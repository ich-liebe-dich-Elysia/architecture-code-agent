@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0ArchitectureAgent.exe" (
    start "" "%~dp0ArchitectureAgent.exe"
    exit /b 0
)
where py >nul 2>nul
if errorlevel 1 (
    echo Python is not installed. Install Python 3.11 or newer, or use ArchitectureAgent.exe.
    pause
    exit /b 1
)
py -3 desktop_entry.py
if errorlevel 1 pause
