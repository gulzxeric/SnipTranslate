@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "%~dp0run.py"
    exit /b 0
)
echo Python environment not found.
echo Open PowerShell in this folder and run:
echo   py -3 -m venv .venv
echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
echo Then run Start.cmd again.
pause
exit /b 1
