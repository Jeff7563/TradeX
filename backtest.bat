@echo off
REM Backtest the signal rules on past MT5 prices (about 1 year of M15).
cd /d %~dp0
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
.venv\Scripts\python -m server.backtest %*
pause
