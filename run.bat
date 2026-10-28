@echo off
REM Start TradeX on Windows. First run creates a virtual env and installs packages.
cd /d %~dp0
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
if not exist config.json copy config.example.json config.json
start "" http://localhost:8000
.venv\Scripts\python -m uvicorn server.app:app --host 127.0.0.1 --port 8000
