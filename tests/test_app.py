import os, tempfile, unittest
from datetime import date
import app as finsight

class FinSightTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.NamedTemporaryFile(delete=False); self.tmp.close()
        finsight.app.config["TESTING"]=True
        finsight.DB_PATH=self.tmp.name
        finsight.init_db()
        self.client=finsight.app.test_client()
        self.client.post("/register",data={"name":"Test User","email":"test@example.com","password":"password123"},follow_redirects=True)
    def tearDown(self):
        try: os.unlink(self.tmp.name)
        except OSError: pass
    def test_dashboard_requires_auth(self):
        self.client.post("/logout")
        r=self.client.get("/dashboard")
        self.assertEqual(r.status_code,302)
    def test_create_transaction_and_summary(self):
        today=date.today().isoformat()
        r=self.client.post("/transactions/new",data={"description":"Grocery supermarket","amount":"1200","txn_date":today,"txn_type":"expense","category":"Groceries"},follow_redirects=True)
        self.assertEqual(r.status_code,200)
        r=self.client.get("/api/summary?month="+today[:7])
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json["expense"],1200)
    def test_categories(self):
        self.assertEqual(finsight.categorize("Uber trip"),"Transport")
        self.assertEqual(finsight.categorize("Monthly salary","income"),"Salary")
    def test_user_scoped_delete(self):
        with finsight.db() as c:
            c.execute("INSERT INTO users(name,email,password_hash) VALUES(?,?,?)",("Other","other@example.com","x"))
            other=c.execute("SELECT id FROM users WHERE email='other@example.com'").fetchone()["id"]
            c.execute("INSERT INTO transactions(user_id,txn_date,description,amount,txn_type,category) VALUES(?,?,?,?,?,?)",(other,date.today().isoformat(),"Private",50,"expense","Other"))
            txn=c.execute("SELECT id FROM transactions WHERE user_id=?",(other,)).fetchone()["id"]
        self.client.post(f"/transactions/{txn}/delete",follow_redirects=True)
        with finsight.db() as c:
            self.assertIsNotNone(c.execute("SELECT id FROM transactions WHERE id=?",(txn,)).fetchone())
if __name__=="__main__": unittest.main()
