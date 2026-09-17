@echo off
setlocal
cd /d "%~dp0"

rem Competition hardware profile. Change COM6 here only if Device Manager
rem assigns a different outgoing Bluetooth serial port.
set "YINBAN_MODE=hardware"
set "YINBAN_ROBOT_PORT=COM6"
set "YINBAN_ROBOT_BAUD=115200"

echo Starting Yinban...
echo Keep this window open while using the website.
echo Open http://127.0.0.1:8000 in Edge or Chrome.
echo Robot link: Bluetooth serial COM6 with automatic reconnect.
echo The PowerShell window will also show the address for other computers.
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1"

if errorlevel 1 (
  echo.
  echo Yinban failed to start. Please keep this window open and check the error above.
  pause
)

endlocal
