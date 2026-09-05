@echo off
setlocal enabledelayedexpansion

:: Ensure working directory is always set to the directory containing this script
cd /d "%~dp0"

set "PYTHON_EXE="
set "PYTHON_ARGS="

:: 1. Check for local virtual environment (.venv, venv, env)
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
    goto :found_python
)
if exist "%~dp0venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
    goto :found_python
)
if exist "%~dp0env\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0env\Scripts\python.exe"
    goto :found_python
)

:: 2. Check if 'python' command in PATH is valid (not a Windows Store placeholder)
python -c "import sys" >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE=python"
    goto :found_python
)

:: 3. Check Windows Python Launcher ('py')
py -3 -c "import sys" >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE=py"
    set "PYTHON_ARGS=-3"
    goto :found_python
)
py -c "import sys" >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE=py"
    goto :found_python
)

:: 4. Search standard system Python installation paths
for %%D in (
    "C:\Python314"
    "C:\Python313"
    "C:\Python312"
    "C:\Python311"
    "C:\Python310"
    "C:\Python39"
    "C:\Python38"
    "%LocalAppData%\Programs\Python\Python314"
    "%LocalAppData%\Programs\Python\Python313"
    "%LocalAppData%\Programs\Python\Python312"
    "%LocalAppData%\Programs\Python\Python311"
    "%LocalAppData%\Programs\Python\Python310"
    "%LocalAppData%\Programs\Python\Python39"
    "%LocalAppData%\Programs\Python\Python38"
    "%ProgramFiles%\Python314"
    "%ProgramFiles%\Python313"
    "%ProgramFiles%\Python312"
    "%ProgramFiles%\Python311"
    "%ProgramFiles%\Python310"
    "%ProgramFiles%\Python39"
    "%ProgramFiles%\Python38"
    "%ProgramFiles(x86)%\Python314"
    "%ProgramFiles(x86)%\Python313"
    "%ProgramFiles(x86)%\Python312"
    "%ProgramFiles(x86)%\Python311"
    "%ProgramFiles(x86)%\Python310"
    "%UserProfile%\anaconda3"
    "%UserProfile%\miniconda3"
) do (
    if exist "%%~D\python.exe" (
        set "PYTHON_EXE=%%~D\python.exe"
        goto :found_python
    )
)

:: 5. Wildcard search in user & system folders
for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" (
        set "PYTHON_EXE=%%D\python.exe"
        goto :found_python
    )
)
for /d %%D in ("%ProgramFiles%\Python3*") do (
    if exist "%%D\python.exe" (
        set "PYTHON_EXE=%%D\python.exe"
        goto :found_python
    )
)
for /d %%D in ("C:\Python3*") do (
    if exist "%%D\python.exe" (
        set "PYTHON_EXE=%%D\python.exe"
        goto :found_python
    )
)

:: Python not found error
echo ==================================================
echo ERROR: Python executable was not found on this system.
echo ==================================================
echo Please install Python (3.8 or newer) or add Python to your PATH environment variable.
echo Download Python at: https://www.python.org/
echo.
pause
exit /b 1

:found_python
if "%PYTHON_ARGS%"=="" (
    echo Starting SD-FastBackup using: "%PYTHON_EXE%"
    "%PYTHON_EXE%" main.py %*
) else (
    echo Starting SD-FastBackup using: "%PYTHON_EXE%" %PYTHON_ARGS%
    "%PYTHON_EXE%" %PYTHON_ARGS% main.py %*
)

if %errorlevel% neq 0 (
    echo.
    echo Application exited with error code %errorlevel%.
    pause
)