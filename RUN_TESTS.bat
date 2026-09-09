@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto :fail
".venv\Scripts\python.exe" -m pip install -r beam-backend\requirements-dev.txt || goto :fail
".venv\Scripts\python.exe" -m pytest -q beam-backend || goto :fail
".venv\Scripts\python.exe" beam-backend\test_frontend_contract.py || goto :fail
".venv\Scripts\python.exe" beam-backend\test_transport_contract.py || goto :fail
".venv\Scripts\python.exe" tools\build_frontend.py || goto :fail
".venv\Scripts\python.exe" tools\smoke_release.py || goto :fail
".venv\Scripts\python.exe" tools\smoke_v11.py || goto :fail
".venv\Scripts\python.exe" tools\smoke_demo.py || goto :fail
echo All tests and frontend build passed.
pause
exit /b 0
:fail
echo Test failed. Install Python 3.12+ and Node.js 22, then read the error above.
pause
exit /b 1
