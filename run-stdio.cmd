@echo off
setlocal
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  echo Personal Filebridge is not installed. Run setup.ps1 first. 1>&2
  exit /b 1
)
"%PYTHON_EXE%" -m filebridge.server --transport stdio
exit /b %ERRORLEVEL%
