@echo off
REM Start the TradeX signal scanner (sends new setups to LINE).
cd /d %~dp0
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
if not exist config.json copy config.example.json config.json
.venv\Scripts\python -m server.scanner
pause
