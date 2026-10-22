@echo off
setlocal
cd /d "%~dp0"

python --version >nul 2>nul
if not errorlevel 1 goto run_python

py -3 --version >nul 2>nul
if not errorlevel 1 goto run_py

echo.
echo   Python 3.10 or newer was not found on PATH.
echo   Install Python from https://www.python.org/downloads/ and try again.
echo.
pause
exit /b 1

:run_py
py -3 "%~dp0tokentrace.py" %*
goto finished

:run_python
python "%~dp0tokentrace.py" %*
goto finished

:finished
if errorlevel 1 pause
endlocal
