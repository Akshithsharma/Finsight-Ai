@echo off
setlocal
if not exist .venv (
  py -m venv .venv
)
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .env copy .env.example .env
echo.
echo Starting FinSight AI at http://127.0.0.1:5000
python app.py
pause
