@echo off
REM Check a public Telegram signal channel against real MT5 prices.
REM Usage: double-click (checks tradeforex112233, 90 days) or: channel_check.bat <channel> --days 120
cd /d %~dp0
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
if "%~1"=="" (
  .venv\Scripts\python -m server.channel_check tradeforex112233 --days 90
) else (
  .venv\Scripts\python -m server.channel_check %*
)
pause
