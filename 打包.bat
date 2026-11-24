@echo off
setlocal
rem Build the exe with PyInstaller. Output goes to dist\.
rem Keep this file ASCII-only, no BOM: cmd.exe parses .bat in the OEM codepage.

set "HERE=%~dp0"
set "PY=%HERE%.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" -m PyInstaller --noconfirm --clean --windowed ^
    --distpath dist ^
    --name 隐络双层PDF制作器 ^
    --icon assets/icon.ico ^
    --add-data "assets/icon.ico;assets" ^
    --paths "%HERE%" ^
    --collect-all rapidocr_onnxruntime ^
    --collect-all onnxruntime ^
    main.py

echo.
echo Output: %HERE%dist\隐络双层PDF制作器\
pause
