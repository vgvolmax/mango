@echo off
setlocal
set "APP_ROOT=%~dp0"
set "MANGO_APP_ROOT=%APP_ROOT%"
if not exist "%APP_ROOT%runtime\pythonw.exe" (
  echo Portable runtime not found. Download a release package or run Build-Portable.bat as a developer.
  pause
  exit /b 1
)
start "" /D "%APP_ROOT%" "%APP_ROOT%runtime\pythonw.exe" -m app.main
endlocal
