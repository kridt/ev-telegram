@echo off
echo Starting Soccer Value Scanner...
echo.
echo The scanner runs every 5 minutes and sends alerts to Telegram.
echo Press Ctrl+C to stop.
echo.
cd /d "%~dp0"
python -u auto_scanner.py
pause
