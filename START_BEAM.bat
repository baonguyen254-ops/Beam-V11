@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run INSTALL_BEAM.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" RUN_BEAM.py --demo --open
if errorlevel 1 pause
