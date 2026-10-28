@echo off
REM Compare 54 rule settings on past MT5 prices (train on first half, check on second half).
REM The summary is also saved to optimize_report.txt
cd /d %~dp0
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
.venv\Scripts\python -m server.optimize %*
pause
