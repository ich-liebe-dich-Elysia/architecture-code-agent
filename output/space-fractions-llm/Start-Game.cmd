@echo off
setlocal
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 (
  echo Node.js is missing. Install Node.js 22 or newer, then reopen this file.
  pause
  exit /b 1
)
if not exist "node_modules\express" (
  where npm.cmd >nul 2>nul
  if errorlevel 1 (
    echo npm is missing. Reinstall Node.js with npm, then reopen this file.
    pause
    exit /b 1
  )
  echo Installing game dependencies...
  call npm.cmd install --ignore-scripts --no-audit --no-fund
  if errorlevel 1 (
    echo Dependency installation failed. Check your network and try again.
    pause
    exit /b 1
  )
)
set "NODE_ENV=production"
set "DEEPSEEK_API_KEY="
set "OPENAI_API_KEY="
node launch_game.cjs
if errorlevel 1 (echo The game could not start. See the error above. & pause & exit /b 1)
