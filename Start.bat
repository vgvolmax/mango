@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0scripts\launcher\bootstrap.ps1" %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
  echo.
  echo MANGO Downloader could not start.
  echo Log: "%~dp0logs\launcher.log"
  if not defined CI pause
)
exit /b %RC%
