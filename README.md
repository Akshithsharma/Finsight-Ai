# FinSight AI — Personal Finance Analyzer

A full-stack, locally runnable personal-finance web application built with Flask, SQLite, HTML/CSS/JavaScript and Chart.js. It provides account registration/login, transaction management, rule-based auto-categorization, monthly dashboards, budgets, savings goals, CSV import/export, spending insights, and statistical unusual-transaction flags.

> **Scope and honest limits:** This is a complete functional application for manual/CSV-based personal finance tracking. It does not connect to banks, make investment recommendations, or use an external generative-AI model by default. Expense classification is rule-based and anomaly flags are statistical heuristics—not financial advice. Bank synchronization, production-grade multi-factor authentication, email verification, password resets, and regulatory compliance are not included. Do not expose this personal-finance app to the public internet without a security review.

## Features
- User registration, sign-in, sign-out, hashed passwords, per-user data separation.
- Responsive dashboard with income, expenses, net cash flow, category charts, daily trend, budgets and narrative insights.
- Add/edit/delete income and expense transactions; merchant, notes and recurring marker.
- Rule-based category suggestions through CSV import; CSV export.
- Monthly category budgets with progress and over-budget indicators.
- Savings goals with target/current balance and completion progress.
- Statistical anomaly hints using per-category mean and standard deviation, plus large-transaction review flags.
- Sample data for exploring the app.
- JSON endpoint `/api/summary?month=YYYY-MM`.
- Currency preferences for INR, USD, EUR, GBP, CAD and AUD.

## Run on Windows 10/11
1. Install Python 3.10+ from https://www.python.org/downloads/ and enable **Add Python to PATH**.
2. Extract this ZIP to a folder.
3. Double-click `run_windows.bat`.
4. Open http://127.0.0.1:5000.
5. Register an account. To populate a demo account, choose **Load sample data** on the dashboard.

If the batch file fails, open Command Prompt in this folder and run:
```bat
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
python app.py
```

## Run on macOS/Linux
```bash
chmod +x run_mac_linux.sh
./run_mac_linux.sh
```
Then open http://127.0.0.1:5000.

## CSV import format
Required headers: `Date`, `Description`, `Amount`. Optional: `Type`, `Category`.
- Date must be ISO format: `YYYY-MM-DD`.
- Amount must be positive for ordinary expense rows. If `Type` is absent, a negative amount is interpreted as income and converted to an absolute value.
- Example:
```csv
Date,Description,Amount,Type,Category
2026-10-01,Monthly salary,52000,income,Salary
2026-10-02,Grocery supermarket,1200,expense,Groceries
```

## Configuration
Copy `.env.example` to `.env` and set a unique `FINSIGHT_SECRET_KEY`. The application loads `.env` automatically when `python-dotenv` is installed. Never deploy with the example secret. Set `FINSIGHT_DB` to a persistent absolute path if needed.

## Test
Install dependencies, then run:
```bash
python -m unittest discover -s tests -v
```

## Project structure
```
app.py
requirements.txt
.env.example
run_windows.bat
run_mac_linux.sh
templates/
static/
tests/
```

## Production checklist
- Replace the secret key; use HTTPS and secure cookie settings.
- Add CSRF protection to forms and rate limiting to login/register.
- Add verified email, password reset, MFA, audit logging and backup/restore.
- Use a production WSGI server and persistent managed database; add migrations.
- Add privacy policy, terms, retention/deletion controls and jurisdiction-specific compliance review.
- Conduct dependency, authorization, upload and penetration testing.
- Avoid storing bank credentials. Bank integrations require a trusted regulated provider and user consent.
