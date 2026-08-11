@echo off
setlocal
cd /d "%~dp0"

set "BUILD_PYTHON=%~1"
if not defined BUILD_PYTHON (
  for /f "usebackq delims=" %%I in (`python -c "import sys; print(sys.executable)" 2^>nul`) do set "BUILD_PYTHON=%%I"
)
if not defined BUILD_PYTHON (
  echo Python 3.12 with pip is required to build the portable package.
  exit /b 1
)

powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0scripts\build_portable.ps1" -BuildPython "%BUILD_PYTHON%"
exit /b %errorlevel%
