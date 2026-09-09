@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" python -m venv .venv
".venv\Scripts\python.exe" -m pip install -r beam-backend\requirements-dev.txt || goto :fail
".venv\Scripts\python.exe" tools\build_frontend.py || goto :fail
echo Development tools installed and frontend built.
pause
exit /b 0
:fail
echo Development installation failed. Read the error above.
pause
exit /b 1
