@echo off
REM Collection now runs unattended in GitHub Actions (.github/workflows/daily-collect.yml),
REM so this no longer calls the API. It just pulls the latest collected data down
REM so the local dashboard matches what the cloud has already gathered.
REM
REM To collect manually anyway (e.g. the workflow is disabled):
REM   py scripts\collector.py --real  &&  py scripts\pipeline.py
cd /d "%~dp0\.."
echo Pulling latest collected data...
git pull --ff-only
if errorlevel 1 (
  echo.
  echo Pull failed. If you have local edits, check: git status
  pause & exit /b 1
)
echo.
echo Up to date. Open dashboard\index.html to view.
pause
