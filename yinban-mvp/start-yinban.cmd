@echo off
setlocal
cd /d "%~dp0"

echo Starting Yinban...
echo Keep this window open while using the website.
echo Open http://127.0.0.1:8000 in Edge or Chrome.
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1"

if errorlevel 1 (
  echo.
  echo Yinban failed to start. Please keep this window open and check the error above.
  pause
)

endlocal
