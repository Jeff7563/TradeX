@echo off
REM Compare 54 rule settings on past MT5 prices (train on first half, check on second half).
cd /d %~dp0
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
.venv\Scripts\python -m server.optimize %* > optimize_report.txt 2>&1
type optimize_report.txt
echo.
echo ผลทั้งหมดบันทึกใน optimize_report.txt และ optimize_results.csv
pause
