@echo off
cd /d "%~dp0"
if exist "%~dp0PersonalFilebridge.exe" (
  "%~dp0PersonalFilebridge.exe" --dashboard
  if errorlevel 1 pause
  exit /b %ERRORLEVEL%
)
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Run install.cmd first.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -m filebridge.dashboard
if errorlevel 1 (
  echo Dashboard could not open. See README.md for troubleshooting.
  pause
)
