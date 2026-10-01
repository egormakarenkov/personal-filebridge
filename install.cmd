@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
if errorlevel 1 (
  echo.
  echo Installation stopped. Read the error above, then see README.md.
) else (
  echo.
  echo Installation complete. Restart your MCP client, then ask it to call health.
)
pause
