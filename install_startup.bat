@echo off
echo Installing Soccer Value Scanner to Windows Startup...

:: Kill any existing scanner
taskkill /F /IM python.exe /FI "WINDOWTITLE eq auto_scanner*" 2>nul

:: Create shortcut in Startup folder
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set SCRIPT=%~dp0run_hidden.vbs

:: Use PowerShell to create shortcut
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%STARTUP%\SoccerValueScanner.lnk'); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%SCRIPT%\"'; $s.WorkingDirectory = '%~dp0'; $s.Save()"

echo.
echo Done! Scanner will start automatically on Windows boot.
echo.
echo Starting scanner now...
wscript.exe "%SCRIPT%"
echo Scanner is running in background.
echo.
pause
