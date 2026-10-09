@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Create the build environment first:
    echo   py -3 -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r requirements-build.txt
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo Install the build dependency first:
    echo   .venv\Scripts\python.exe -m pip install -r requirements-build.txt
    pause
    exit /b 1
)
".venv\Scripts\python.exe" build_executable.py
if errorlevel 1 (
    echo Build failed. See the error above.
    pause
    exit /b 1
)
echo Created: %~dp0ArchitectureAgent.exe
echo Keep the executable beside the agent, input, and output directories.
exit /b 0
