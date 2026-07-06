@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Starting Life Copy Workbench...
echo.

if not exist "rensheng-fuben.exe" (
  echo rensheng-fuben.exe was not found in this folder.
  echo Please extract the whole zip package before starting.
  echo.
  pause
  exit /b 1
)

"%~dp0rensheng-fuben.exe"
set EXIT_CODE=%ERRORLEVEL%

echo.
if not "%EXIT_CODE%"=="0" (
  echo Startup failed. Error code: %EXIT_CODE%
  echo If startup-error.log exists in this folder, send it to the developer.
) else (
  echo The workbench has exited.
)
echo.
pause
