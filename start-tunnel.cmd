@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-tunnel.ps1" %*
if errorlevel 1 (
  echo.
  echo Tunnel startup failed. Review the error message above.
  pause
)
