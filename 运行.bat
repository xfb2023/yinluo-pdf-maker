@echo off
setlocal
rem Launch the app with local .venv if present, else system Python.
rem Keep this file ASCII-only, no BOM: cmd.exe parses .bat in the OEM codepage.

set "HERE=%~dp0"
set "PYW=%HERE%.venv\Scripts\pythonw.exe"
if exist "%PYW%" goto run
where pythonw >nul 2>nul
if %errorlevel%==0 (
    set "PYW=pythonw"
    goto run
)
echo [ERROR] Python not found. Install Python 3.10+ and run: pip install -r requirements.txt
pause
exit /b 1

:run
start "" "%PYW%" "%HERE%main.py"
exit /b 0
