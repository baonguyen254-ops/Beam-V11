@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Run INSTALL_BEAM.bat first.
  pause
  exit /b 1
)
if "%~1"=="" (
  echo Usage: IMPORT_OPENSTUDIO_REPORT.bat "C:\path\to\report.html"
  echo.
  echo The importer writes beam-backend\data\energy_baseline.json.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "beam-backend\tools\import_openstudio_report.py" "%~1" --output "beam-backend\data\energy_baseline.json"
if errorlevel 1 (
  echo [ERROR] Import failed.
  pause
  exit /b 1
)
echo.
echo [OK] OpenStudio report imported. Restart B.E.A.M. so the backend reloads the baseline.
pause
