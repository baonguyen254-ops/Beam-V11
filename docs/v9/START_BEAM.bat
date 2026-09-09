@echo off
setlocal
set "ROOT=%~dp0"

if exist "%ROOT%.venv\Scripts\python.exe" (
  start "B.E.A.M. v9 Backend" cmd /k "cd /d ""%ROOT%beam-backend"" && ""%ROOT%.venv\Scripts\python.exe"" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
) else (
  start "B.E.A.M. v9 Backend" cmd /k "cd /d ""%ROOT%beam-backend"" && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
)
start "B.E.A.M. v9 Frontend" cmd /k "cd /d ""%ROOT%beam-frontend"" && npm run dev"

echo B.E.A.M. v9 launched.
echo Backend health: http://127.0.0.1:8000/health
echo Frontend:       http://localhost:5173
endlocal
