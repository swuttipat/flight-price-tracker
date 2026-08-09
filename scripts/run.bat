@echo off
REM Manual flight price tracker run: collect real prices, rebuild dashboard data.
cd /d "%~dp0"
set PY=py
where py >nul 2>nul || set PY=python
echo Collecting real prices (book + calendar)...
%PY% collector.py --real
if errorlevel 1 (
  echo.
  echo Collection failed. Check TRAVELPAYOUTS_TOKEN is set and you have internet.
  pause & exit /b 1
)
echo Rebuilding dashboard data...
%PY% pipeline.py
echo.
echo Done. Open dashboard\index.html to view.
pause
