@echo off
setlocal
set ROOT=%~dp0
cd /d "%ROOT%"

echo [1/4] Checking Python...
python --version || goto :fail

echo [2/4] Creating/updating local Python environment...
if not exist ".venv\Scripts\python.exe" python -m venv .venv
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r "beam-backend\requirements.txt" || goto :fail

echo [3/4] Checking Node/npm...
node --version || goto :fail
npm --version || goto :fail

echo [4/4] Installing frontend packages...
pushd "beam-frontend"
call npm install || goto :npmfail
popd

echo.
echo B.E.A.M. v9 installation complete.
echo Run START_BEAM.bat next.
pause
exit /b 0

:npmfail
popd
:fail
echo.
echo INSTALLATION FAILED. Read README.md Troubleshooting section.
pause
exit /b 1
