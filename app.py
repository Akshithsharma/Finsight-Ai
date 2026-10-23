import os, csv, io, sqlite3, secrets, hashlib, hmac, json, re
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass
from datetime import date, datetime, timedelta
from functools import wraps
from collections import defaultdict
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file, abort
from werkzeug.security import generate_password_hash, check_password_hash

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("FINSIGHT_DB", "/tmp/finsight.db" if os.environ.get("VERCEL") else os.path.join(APP_DIR, "finsight.db"))
SECRET_KEY = os.environ.get("FINSIGHT_SECRET_KEY", "CHANGE-ME-before-deployment-" + secrets.token_hex(12))
app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
CATEGORIES = ["Food & Dining","Groceries","Transport","Housing","Utilities","Healthcare","Shopping","Entertainment","Education","Travel","Income","Salary","Investment","Transfer","Fees","Other"]
INCOME_CATEGORIES = {"Income","Salary","Investment"}
DEFAULT_CURRENCY = "INR"

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
          password_hash TEXT NOT NULL, currency TEXT NOT NULL DEFAULT 'INR',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS transactions(
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          txn_date TEXT NOT NULL, description TEXT NOT NULL, merchant TEXT DEFAULT '',
          amount REAL NOT NULL CHECK(amount > 0), txn_type TEXT NOT NULL CHECK(txn_type IN ('income','expense')),
          category TEXT NOT NULL DEFAULT 'Other', notes TEXT DEFAULT '', is_recurring INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS idx_txn_user_date ON transactions(user_id, txn_date);
        CREATE TABLE IF NOT EXISTS budgets(
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          month TEXT NOT NULL, category TEXT NOT NULL, amount REAL NOT NULL CHECK(amount >= 0),
          UNIQUE(user_id, month, category));
        CREATE TABLE IF NOT EXISTS goals(
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          name TEXT NOT NULL, target_amount REAL NOT NULL CHECK(target_amount > 0),
          current_amount REAL NOT NULL DEFAULT 0 CHECK(current_amount >= 0),
          target_date TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        """)
init_db()

def current_user():
    uid = session.get("user_id")
    if not uid: return None
    with db() as c: return c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()

app.jinja_env.globals["current_user"] = current_user

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper

def money(value, currency="INR"):
    try: value = float(value or 0)
    except (ValueError, TypeError): value = 0
    symbol = {"INR":"₹","USD":"$","EUR":"€","GBP":"£","CAD":"CA$","AUD":"A$"}.get(currency, currency+" ")
    return f"{symbol}{value:,.2f}"

app.jinja_env.filters["money"] = money

def categorize(description, txn_type="expense"):
    d = (description or "").lower()
    if txn_type == "income":
        if any(x in d for x in ["salary","payroll","wage"]): return "Salary"
        if any(x in d for x in ["dividend","interest","stock","mutual fund","investment"]): return "Investment"
        return "Income"
    rules = [
        ("Food & Dining", ["restaurant","cafe","coffee","swiggy","zomato","pizza","burger","food","hotel dining"]),
        ("Groceries", ["grocery","supermarket","vegetables","milk","bigbasket","blinkit","zepto"]),
        ("Transport", ["uber","ola","fuel","petrol","diesel","metro","bus","train","rapido","parking"]),
        ("Housing", ["rent","landlord","mortgage","hostel"]),
        ("Utilities", ["electricity","water bill","internet","wifi","broadband","mobile recharge","gas bill"]),
        ("Healthcare", ["hospital","doctor","pharmacy","medicine","clinic","health"]),
        ("Shopping", ["amazon","flipkart","myntra","shopping","clothing","electronics"]),
        ("Entertainment", ["netflix","spotify","movie","cinema","game","subscription"]),
        ("Education", ["course","udemy","coursera","college","tuition","books"]),
        ("Travel", ["flight","airline","hotel booking","airbnb","makemytrip","irctc"]),
        ("Fees", ["bank fee","late fee","service charge","interest charge"]),
        ("Transfer", ["transfer","upi to","sent to"]),
    ]
    for cat, words in rules:
        if any(w in d for w in words): return cat
    return "Other"

def month_bounds(month):
    try:
        y, m = map(int, month.split("-"))
        start = date(y,m,1)
        end = date(y+1,1,1) if m == 12 else date(y,m+1,1)
        return start.isoformat(), end.isoformat()
    except Exception:
        today=date.today(); start=date(today.year,today.month,1)
        end=date(today.year+1,1,1) if today.month==12 else date(today.year,today.month+1,1)
        return start.isoformat(), end.isoformat()

def get_transactions(uid, start=None, end=None):
    q = "SELECT * FROM transactions WHERE user_id=?"; args=[uid]
    if start: q += " AND txn_date>=?"; args.append(start)
    if end: q += " AND txn_date<?"; args.append(end)
    q += " ORDER BY txn_date DESC, id DESC"
    with db() as c: return c.execute(q,args).fetchall()

def dashboard_data(uid, month):
    start,end=month_bounds(month)
    rows=get_transactions(uid,start,end)
    income=sum(r["amount"] for r in rows if r["txn_type"]=="income")
    expense=sum(r["amount"] for r in rows if r["txn_type"]=="expense")
    bycat=defaultdict(float)
    byday=defaultdict(lambda: {"income":0.0,"expense":0.0})
    for r in rows:
        if r["txn_type"]=="expense": bycat[r["category"]]+=r["amount"]
        byday[r["txn_date"]][r["txn_type"]]+=r["amount"]
    with db() as c:
        budgets=c.execute("SELECT * FROM budgets WHERE user_id=? AND month=?", (uid,month)).fetchall()
    budget_map={b["category"]:b["amount"] for b in budgets}
    budget_cards=[]
    for cat,amount in sorted(budget_map.items()):
        spent=bycat.get(cat,0)
        budget_cards.append({"category":cat,"budget":amount,"spent":spent,"pct":min(100,round(spent/amount*100,1)) if amount else 0,"over":spent>amount})
    prev_month=(date.fromisoformat(start)-timedelta(days=1)).strftime("%Y-%m")
    ps,pe=month_bounds(prev_month)
    prev=get_transactions(uid,ps,pe)
    prev_exp=sum(r["amount"] for r in prev if r["txn_type"]=="expense")
    change=((expense-prev_exp)/prev_exp*100) if prev_exp else None
    return {"income":income,"expense":expense,"net":income-expense,"count":len(rows),
            "categories":dict(sorted(bycat.items(),key=lambda x:x[1],reverse=True)),
            "days":sorted([{"date":d,"income":v["income"],"expense":v["expense"]} for d,v in byday.items()],key=lambda x:x["date"]),
            "budgets":budget_cards,"prev_expense":prev_exp,"expense_change":change}

def detect_anomalies(uid):
    rows=get_transactions(uid)
    groups=defaultdict(list)
    for r in rows:
        if r["txn_type"]=="expense": groups[r["category"]].append(float(r["amount"]))
    stats={}
    for cat, vals in groups.items():
        if len(vals)>=3:
            mean=sum(vals)/len(vals)
            variance=sum((v-mean)**2 for v in vals)/len(vals)
            stats[cat]=(mean,variance**0.5)
    anomalies=[]
    for r in rows:
        if r["txn_type"]!="expense": continue
        mean,sd=stats.get(r["category"],(0,0))
        reason=None
        if len(groups[r["category"]])>=3 and sd>0 and r["amount"] > mean+2*sd:
            reason=f"Amount is unusually high for {r['category']} (usual average {mean:,.2f})."
        elif r["amount"] >= 10000:
            reason="Large transaction: review that this purchase was expected."
        if reason: anomalies.append({"transaction":r,"reason":reason})
    return anomalies[:30]

def insights(uid, month):
    data=dashboard_data(uid,month); msgs=[]
    if data["expense"] == 0:
        msgs.append("No expenses recorded for this month yet. Add or import transactions to unlock spending insights.")
    else:
        top=next(iter(data["categories"].items()),None)
        if top: msgs.append(f"{top[0]} is your largest expense category at {money(top[1])}.")
        if data["income"] and data["net"]<0: msgs.append("Your recorded expenses exceed income this month. Review flexible spending and upcoming bills.")
        elif data["income"] and data["net"]>=0: msgs.append(f"You have a positive cash flow of {money(data['net'])} this month.")
        if data["expense_change"] is not None:
            if data["expense_change"]>10: msgs.append(f"Expenses are up {data['expense_change']:.1f}% versus last month.")
            elif data["expense_change"]<-10: msgs.append(f"Expenses are down {abs(data['expense_change']):.1f}% versus last month.")
        over=[b for b in data["budgets"] if b["over"]]
        for b in over[:3]: msgs.append(f"{b['category']} is over budget by {money(b['spent']-b['budget'])}.")
    return msgs

@app.route("/")
def index():
    if current_user(): return redirect(url_for("dashboard"))
    return render_template("landing.html")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        name=request.form.get("name","").strip()
        email=request.form.get("email","").strip().lower()
        password=request.form.get("password","")
        if len(name)<2 or "@" not in email or len(password)<8:
            flash("Enter a name, valid email, and password of at least 8 characters.", "danger")
            return render_template("auth.html", mode="register")
        try:
            with db() as c:
                cur=c.execute("INSERT INTO users(name,email,password_hash) VALUES(?,?,?)",(name,email,generate_password_hash(password)))
                uid=cur.lastrowid
            session.clear(); session["user_id"]=uid
            flash("Account created. Add transactions or load sample data to explore FinSight.", "success")
            return redirect(url_for("dashboard"))
        except sqlite3.IntegrityError:
            flash("An account with that email already exists. Please sign in.", "warning")
    return render_template("auth.html",mode="register")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email=request.form.get("email","").strip().lower(); password=request.form.get("password","")
        with db() as c: user=c.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
        if user and check_password_hash(user["password_hash"],password):
            session.clear(); session["user_id"]=user["id"]
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Email or password is incorrect.", "danger")
    return render_template("auth.html",mode="login")

@app.route("/logout",methods=["POST"])
def logout():
    session.clear(); return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    user=current_user(); month=request.args.get("month",date.today().strftime("%Y-%m"))
    data=dashboard_data(user["id"],month)
    return render_template("dashboard.html",user=user,month=month,data=data,insights=insights(user["id"],month),
                           anomalies=detect_anomalies(user["id"])[:5],categories=CATEGORIES)

@app.route("/transactions")
@login_required
def transactions():
    user=current_user()
    month=request.args.get("month","")
    start,end=month_bounds(month) if re.fullmatch(r"\d{4}-\d{2}",month) else (None,None)
    rows=get_transactions(user["id"],start,end)
    return render_template("transactions.html",user=user,rows=rows,month=month,categories=CATEGORIES)

@app.route("/transactions/new",methods=["GET","POST"])
@login_required
def new_transaction():
    user=current_user()
    if request.method=="POST":
        try:
            amount=round(float(request.form.get("amount","")),2)
            txn_date=request.form.get("txn_date","")
            description=request.form.get("description","").strip()
            txn_type=request.form.get("txn_type","expense")
            category=request.form.get("category","Other")
            if amount<=0 or not description or txn_type not in ("income","expense") or category not in CATEGORIES:
                raise ValueError()
            date.fromisoformat(txn_date)
            with db() as c:
                c.execute("""INSERT INTO transactions(user_id,txn_date,description,merchant,amount,txn_type,category,notes,is_recurring)
                VALUES(?,?,?,?,?,?,?,?,?)""",(user["id"],txn_date,description,request.form.get("merchant","").strip(),amount,txn_type,category,request.form.get("notes","").strip(),1 if request.form.get("is_recurring") else 0))
            flash("Transaction added.", "success"); return redirect(url_for("transactions"))
        except (ValueError,TypeError):
            flash("Please enter a valid date, description, category, type, and positive amount.", "danger")
    return render_template("transaction_form.html",user=user,categories=CATEGORIES,today=date.today().isoformat())

@app.route("/transactions/<int:txn_id>/edit",methods=["GET","POST"])
@login_required
def edit_transaction(txn_id):
    user=current_user()
    with db() as c: row=c.execute("SELECT * FROM transactions WHERE id=? AND user_id=?",(txn_id,user["id"])).fetchone()
    if not row: abort(404)
    if request.method=="POST":
        try:
            amount=round(float(request.form["amount"]),2); txn_date=request.form["txn_date"]
            date.fromisoformat(txn_date)
            desc=request.form["description"].strip(); typ=request.form["txn_type"]; cat=request.form["category"]
            if amount<=0 or not desc or typ not in ("income","expense") or cat not in CATEGORIES: raise ValueError()
            with db() as c:
                c.execute("""UPDATE transactions SET txn_date=?,description=?,merchant=?,amount=?,txn_type=?,category=?,notes=?,is_recurring=? WHERE id=? AND user_id=?""",
                          (txn_date,desc,request.form.get("merchant","").strip(),amount,typ,cat,request.form.get("notes","").strip(),1 if request.form.get("is_recurring") else 0,txn_id,user["id"]))
            flash("Transaction updated.", "success"); return redirect(url_for("transactions"))
        except (ValueError,TypeError,KeyError):
            flash("Please check the transaction details.", "danger")
    return render_template("transaction_form.html",user=user,categories=CATEGORIES,today=date.today().isoformat(),row=row)

@app.route("/transactions/<int:txn_id>/delete",methods=["POST"])
@login_required
def delete_transaction(txn_id):
    with db() as c: c.execute("DELETE FROM transactions WHERE id=? AND user_id=?",(txn_id,current_user()["id"]))
    flash("Transaction deleted if it belonged to your account.", "success"); return redirect(url_for("transactions"))

@app.route("/budgets",methods=["GET","POST"])
@login_required
def budgets():
    user=current_user(); month=request.args.get("month",date.today().strftime("%Y-%m"))
    if request.method=="POST":
        month=request.form.get("month",month); cat=request.form.get("category",""); 
        try: amount=round(float(request.form.get("amount","")),2)
        except: amount=-1
        if not re.fullmatch(r"\d{4}-\d{2}",month) or cat not in CATEGORIES or cat in INCOME_CATEGORIES or amount<0:
            flash("Enter a valid month, expense category, and non-negative budget.", "danger")
        else:
            with db() as c:
                c.execute("INSERT INTO budgets(user_id,month,category,amount) VALUES(?,?,?,?) ON CONFLICT(user_id,month,category) DO UPDATE SET amount=excluded.amount",(user["id"],month,cat,amount))
            flash("Budget saved.", "success")
        return redirect(url_for("budgets",month=month))
    data=dashboard_data(user["id"],month)
    with db() as c: items=c.execute("SELECT * FROM budgets WHERE user_id=? AND month=? ORDER BY category",(user["id"],month)).fetchall()
    expense_cats=[x for x in CATEGORIES if x not in INCOME_CATEGORIES and x!="Transfer"]
    return render_template("budgets.html",user=user,month=month,items=items,data=data,expense_categories=expense_cats)

@app.route("/budgets/<int:budget_id>/delete",methods=["POST"])
@login_required
def delete_budget(budget_id):
    with db() as c: c.execute("DELETE FROM budgets WHERE id=? AND user_id=?",(budget_id,current_user()["id"]))
    flash("Budget deleted.", "success"); return redirect(url_for("budgets"))

@app.route("/goals",methods=["GET","POST"])
@login_required
def goals():
    user=current_user()
    if request.method=="POST":
        name=request.form.get("name","").strip()
        try: target=float(request.form.get("target_amount","")); current=float(request.form.get("current_amount","0"))
        except: target=-1; current=-1
        target_date=request.form.get("target_date","")
        if not name or target<=0 or current<0 or (target_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}",target_date)):
            flash("Enter a goal name, positive target, and valid current savings.", "danger")
        else:
            with db() as c: c.execute("INSERT INTO goals(user_id,name,target_amount,current_amount,target_date) VALUES(?,?,?,?,?)",(user["id"],name,target,current,target_date))
            flash("Savings goal created.", "success")
        return redirect(url_for("goals"))
    with db() as c: items=c.execute("SELECT * FROM goals WHERE user_id=? ORDER BY id DESC",(user["id"],)).fetchall()
    return render_template("goals.html",user=user,items=items)

@app.route("/goals/<int:goal_id>/update",methods=["POST"])
@login_required
def update_goal(goal_id):
    user=current_user()
    try: current=max(0,float(request.form.get("current_amount","0")))
    except: current=0
    with db() as c: c.execute("UPDATE goals SET current_amount=? WHERE id=? AND user_id=?",(current,goal_id,user["id"]))
    flash("Goal updated.", "success"); return redirect(url_for("goals"))

@app.route("/goals/<int:goal_id>/delete",methods=["POST"])
@login_required
def delete_goal(goal_id):
    with db() as c: c.execute("DELETE FROM goals WHERE id=? AND user_id=?",(goal_id,current_user()["id"]))
    flash("Goal deleted.", "success"); return redirect(url_for("goals"))

@app.route("/insights")
@login_required
def insights_page():
    user=current_user(); month=request.args.get("month",date.today().strftime("%Y-%m"))
    return render_template("insights.html",user=user,month=month,messages=insights(user["id"],month),anomalies=detect_anomalies(user["id"]),data=dashboard_data(user["id"],month))

@app.route("/import",methods=["GET","POST"])
@login_required
def import_csv():
    user=current_user()
    if request.method=="POST":
        file=request.files.get("file")
        if not file or not file.filename.lower().endswith(".csv"):
            flash("Choose a CSV file.", "danger"); return redirect(url_for("import_csv"))
        try:
            content=file.stream.read().decode("utf-8-sig")
            reader=csv.DictReader(io.StringIO(content))
            fields={f.strip().lower():f for f in (reader.fieldnames or [])}
            date_key=next((fields[k] for k in ["date","txn_date","transaction date"] if k in fields),None)
            desc_key=next((fields[k] for k in ["description","name","details","merchant"] if k in fields),None)
            amount_key=next((fields[k] for k in ["amount","value","transaction amount"] if k in fields),None)
            type_key=next((fields[k] for k in ["type","transaction type"] if k in fields),None)
            cat_key=next((fields[k] for k in ["category"] if k in fields),None)
            if not (date_key and desc_key and amount_key): raise ValueError("CSV must include Date, Description, and Amount columns.")
            count=0; skipped=0
            with db() as c:
                for r in reader:
                    try:
                        d=date.fromisoformat((r.get(date_key) or "").strip()[:10]).isoformat()
                        desc=(r.get(desc_key) or "").strip()
                        raw=(r.get(amount_key) or "").replace(",","").replace("₹","").replace("$","").strip()
                        amount=abs(float(raw))
                        typ=(r.get(type_key) or "").strip().lower() if type_key else ("income" if float(raw)<0 else "expense")
                        typ="income" if typ in ("income","credit","deposit") else "expense"
                        cat=(r.get(cat_key) or "").strip() if cat_key else categorize(desc,typ)
                        if cat not in CATEGORIES: cat=categorize(desc,typ)
                        if not desc or amount<=0: raise ValueError()
                        c.execute("INSERT INTO transactions(user_id,txn_date,description,merchant,amount,txn_type,category) VALUES(?,?,?,?,?,?,?)",(user["id"],d,desc,desc,amount,typ,cat)); count+=1
                    except Exception: skipped+=1
            flash(f"Imported {count} transactions; skipped {skipped} invalid rows.", "success" if count else "warning")
        except Exception as e: flash(str(e), "danger")
        return redirect(url_for("transactions"))
    return render_template("import.html",user=user)

@app.route("/export.csv")
@login_required
def export_csv():
    user=current_user(); rows=get_transactions(user["id"])
    output=io.StringIO(); w=csv.writer(output)
    w.writerow(["Date","Description","Merchant","Amount","Type","Category","Notes","Recurring"])
    for r in reversed(rows): w.writerow([r["txn_date"],r["description"],r["merchant"],r["amount"],r["txn_type"],r["category"],r["notes"],"yes" if r["is_recurring"] else "no"])
    data=io.BytesIO(output.getvalue().encode("utf-8-sig"))
    return send_file(data,mimetype="text/csv",as_attachment=True,download_name="finsight_transactions.csv")

@app.route("/sample-data",methods=["POST"])
@login_required
def sample_data():
    uid=current_user()["id"]
    with db() as c:
        existing=c.execute("SELECT COUNT(*) n FROM transactions WHERE user_id=?",(uid,)).fetchone()["n"]
        if existing:
            flash("Sample data is only added to an empty account.", "warning")
        else:
            today=date.today()
            samples=[
             (-1,"Monthly salary",52000,"income","Salary"),(-1,"Freelance project",8500,"income","Income"),
             (-1,"Apartment rent",14500,"expense","Housing"),(-2,"Grocery supermarket",2350,"expense","Groceries"),
             (-3,"Electricity bill",1450,"expense","Utilities"),(-4,"Fuel station",1800,"expense","Transport"),
             (-5,"Restaurant dinner",1250,"expense","Food & Dining"),(-7,"Online shopping",3200,"expense","Shopping"),
             (-8,"Pharmacy",680,"expense","Healthcare"),(-10,"Streaming subscription",499,"expense","Entertainment"),
             (-12,"College course",1800,"expense","Education"),(-14,"Cab ride",420,"expense","Transport"),
             (-17,"Coffee cafe",360,"expense","Food & Dining"),(-20,"Grocery supermarket",1870,"expense","Groceries"),
             (-23,"Restaurant lunch",980,"expense","Food & Dining")]
            for days,desc,amt,typ,cat in samples:
                d=(today+timedelta(days=days)).isoformat()
                c.execute("INSERT INTO transactions(user_id,txn_date,description,merchant,amount,txn_type,category) VALUES(?,?,?,?,?,?,?)",(uid,d,desc,desc,amt,typ,cat))
            month=today.strftime("%Y-%m")
            for cat,amt in [("Groceries",5000),("Food & Dining",3500),("Transport",3000),("Shopping",4000),("Utilities",2500)]:
                c.execute("INSERT OR IGNORE INTO budgets(user_id,month,category,amount) VALUES(?,?,?,?)",(uid,month,cat,amt))
            c.execute("INSERT INTO goals(user_id,name,target_amount,current_amount,target_date) VALUES(?,?,?,?,?)",(uid,"Emergency fund",100000,25000,(today+timedelta(days=365)).isoformat()))
            flash("Sample transactions, budgets and a savings goal added.", "success")
    return redirect(url_for("dashboard"))

@app.route("/api/summary")
@login_required
def api_summary():
    user=current_user(); month=request.args.get("month",date.today().strftime("%Y-%m"))
    d=dashboard_data(user["id"],month)
    return jsonify({"month":month,"income":d["income"],"expense":d["expense"],"net":d["net"],"categories":d["categories"],"days":d["days"],"insights":insights(user["id"],month)})

@app.route("/settings",methods=["GET","POST"])
@login_required
def settings():
    user=current_user()
    if request.method=="POST":
        name=request.form.get("name","").strip(); currency=request.form.get("currency","INR")
        if not name or currency not in ("INR","USD","EUR","GBP","CAD","AUD"):
            flash("Enter a valid name and currency.", "danger")
        else:
            with db() as c: c.execute("UPDATE users SET name=?,currency=? WHERE id=?",(name,currency,user["id"]))
            flash("Settings updated.", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html",user=user)

@app.errorhandler(404)
def not_found(e): return render_template("error.html",code=404,message="We couldn't find that page."),404
@app.errorhandler(500)
def server_error(e): return render_template("error.html",code=500,message="Something went wrong. Check the server log."),500

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST","127.0.0.1"), port=int(os.environ.get("PORT","5000")), debug=os.environ.get("FLASK_DEBUG","0")=="1")
