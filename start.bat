@echo off
rem PaperLook launcher for Windows: double-click to start.
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title PaperLook

rem An environment copied from another computer, or left behind after Python was
rem uninstalled or upgraded, no longer runs: rebuild it.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul || (
    echo [PaperLook] The Python environment is broken, rebuilding it...
    rmdir /s /q ".venv"
  )
)
if exist ".venv\Scripts\python.exe" goto deps

echo [PaperLook] First start: creating the Python environment...
where py >nul 2>nul
if %errorlevel%==0 (py -3 -m venv .venv) else (python -m venv .venv)
if not exist ".venv\Scripts\python.exe" goto nopython
".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" || (
  rmdir /s /q ".venv"
  goto nopython
)

:deps
".venv\Scripts\python.exe" scripts\ensure_deps.py
if errorlevel 1 (
  pause
  exit /b 1
)

set PYTHONPATH=%~dp0backend
".venv\Scripts\python.exe" -m paperlook %*
if errorlevel 1 pause
exit /b

:nopython
echo.
echo [PaperLook] Python 3.11 or newer was not found.
echo   1. Install it from https://www.python.org/downloads/
echo      and tick "Add python.exe to PATH" in the installer.
echo   2. Double-click start.bat again.
start "" "https://www.python.org/downloads/"
pause
exit /b 1
