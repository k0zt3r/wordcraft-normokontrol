@echo off
setlocal
if exist "%~dp0.venv\Scripts\pythonw.exe" goto venv
where pythonw.exe >nul 2>nul
if errorlevel 1 goto console
start "" pythonw.exe "%~dp0normokontrol.py" --gui %*
exit /b
:venv
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0normokontrol.py" --gui %*
exit /b
:console
python "%~dp0normokontrol.py" --gui %*
if errorlevel 1 pause
