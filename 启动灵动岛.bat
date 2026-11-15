@echo off
setlocal
cd /d "%~dp0"
set "APP=%~dp0dynamic_island.py"

rem 1) preferred: pythonw from the local Python 3.13 install (has tkinter)
if exist "%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe" (
    start "" "%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe" "%APP%"
    exit /b 0
)

rem 2) fallback: py launcher windowed edition
where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" pyw -3 "%APP%"
    exit /b 0
)

rem 3) fallback: pythonw from PATH
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%APP%"
    exit /b 0
)

echo [Dynamic Island] Python not found. Install Python 3.9+ (with tkinter) first.
pause
exit /b 1
