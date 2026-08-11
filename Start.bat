@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass ^
  -File "%~dp0scripts\launcher\bootstrap.ps1" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo MANGO Downloader could not start.
  echo Log: "%~dp0.runtime\logs\launcher.log"
  if not defined CI pause
)
exit /b %RC%
