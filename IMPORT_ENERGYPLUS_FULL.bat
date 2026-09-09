@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=python"
if exist "%ROOT%.venv\Scripts\python.exe" set "PYTHON=%ROOT%.venv\Scripts\python.exe"

if "%~1"=="" (
  echo Usage: IMPORT_ENERGYPLUS_FULL.bat "C:\path\to\eplustbl.htm"
  echo.
  echo The imported output becomes beam-backend\data\energy_baseline.json.
  pause
  exit /b 2
)

pushd "%ROOT%beam-backend"
"%PYTHON%" tools\import_energyplus_tabular.py "%~1" --output data\energy_baseline.json
if errorlevel 1 goto :fail
popd

echo.
echo Import complete. Restart the B.E.A.M. backend and check /energy-baseline.
pause
exit /b 0

:fail
popd
echo.
echo Import failed. Check that the file is EnergyPlus eplustbl.htm and that Python dependencies are installed.
pause
exit /b 1
