@echo off
setlocal
cd /d "%~dp0"
python -c "import sys; assert sys.version_info >= (3,12), 'Python 3.12+ required'" || goto :fail
if not exist ".venv\Scripts\python.exe" python -m venv .venv
".venv\Scripts\python.exe" -m pip install -r beam-backend\requirements.txt || goto :fail
echo BEAM v11.1 English Demo installed. Run START_BEAM.bat. No Node.js needed for the bundled UI.
pause
exit /b 0
:fail
echo Install failed. Install Python 3.12+, enable PATH and check network access.
pause
exit /b 1
