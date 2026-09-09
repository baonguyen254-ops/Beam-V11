@echo off
setlocal
set ROOT=%~dp0
set PYTHON=python
if exist "%ROOT%.venv\Scripts\python.exe" set PYTHON=%ROOT%.venv\Scripts\python.exe

echo === Backend regression ===
pushd "%ROOT%beam-backend"
"%PYTHON%" -m pytest -q || goto :fail
"%PYTHON%" test_frontend_contract.py || goto :fail
popd

echo.
echo === Frontend TypeScript ===
pushd "%ROOT%beam-frontend"
call npm run typecheck || goto :npmfail
popd

echo.
echo ALL LOCAL TESTS PASSED.
pause
exit /b 0

:npmfail
popd
:fail
echo TEST FAILURE. See output above.
pause
exit /b 1
