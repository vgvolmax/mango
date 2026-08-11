param(
    [Parameter(Mandatory = $true)]
    [string]$BuildPython
)

$ErrorActionPreference = "Stop"
$PythonVersion = "3.12.8"
$Root = Split-Path -Parent $PSScriptRoot
$Dist = Join-Path $Root "dist"
$Package = Join-Path $Dist "MangoDownloader"
$Cache = Join-Path $Root "build"
$PythonZip = Join-Path $Cache "python-$PythonVersion-embed-amd64.zip"
$PythonUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$BuildPythonError = "Python 3.12 with pip is required to build the portable package."

# Validate the build interpreter before downloading or modifying build output.
if (!(Test-Path -LiteralPath $BuildPython -PathType Leaf)) {
    throw $BuildPythonError
}
$BuildPythonVersion = & $BuildPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0 -or $BuildPythonVersion -ne "3.12") {
    throw $BuildPythonError
}
& $BuildPython -m pip --version | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw $BuildPythonError
}

Remove-Item $Package -Recurse -Force -ErrorAction SilentlyContinue
New-Item $Cache, $Package -ItemType Directory -Force | Out-Null
Write-Host "Downloading embedded Python..."
if (!(Test-Path $PythonZip)) {
    Invoke-WebRequest -UseBasicParsing -Uri $PythonUrl -OutFile $PythonZip
}
if (!(Test-Path $PythonZip) -or (Get-Item $PythonZip).Length -eq 0) {
    throw "Embedded Python download is missing or empty: $PythonZip"
}

$Runtime = Join-Path $Package "runtime"
Expand-Archive $PythonZip $Runtime
$SitePackages = Join-Path $Runtime "Lib\site-packages"
New-Item (Join-Path $Runtime "Lib"), $SitePackages -ItemType Directory -Force | Out-Null

$Pth = Get-ChildItem $Runtime -Filter "python*._pth" | Select-Object -First 1
if ($null -eq $Pth) {
    throw "Embedded Python path configuration was not found in $Runtime"
}
$PthLines = [System.Collections.Generic.List[string]]::new()
foreach ($Line in (Get-Content $Pth.FullName)) {
    if ($Line.Trim() -eq "#import site") {
        $PthLines.Add("import site")
    } else {
        $PthLines.Add($Line)
    }
}
foreach ($RequiredPath in @("python312.zip", ".", "Lib", "Lib/site-packages", "..")) {
    $AlreadyPresent = $PthLines | Where-Object {
        $_.Trim().Replace("\", "/").TrimEnd("/").ToLowerInvariant() -eq
            $RequiredPath.Replace("\", "/").TrimEnd("/").ToLowerInvariant()
    }
    if (!$AlreadyPresent) {
        $PthLines.Add($RequiredPath)
    }
}
if (!(($PthLines | ForEach-Object { $_.Trim() }) -contains "import site")) {
    $PthLines.Add("import site")
}
$PthLines | Set-Content $Pth.FullName -Encoding ASCII

Write-Host "Installing runtime dependencies..."
& $BuildPython -m pip install --disable-pip-version-check --no-compile --target $SitePackages -r (Join-Path $Root "requirements\runtime.txt")
if ($LASTEXITCODE -ne 0) { throw "Runtime dependency installation failed with exit code $LASTEXITCODE" }

Copy-Item (Join-Path $Root "app") $Package -Recurse
@"
@echo off
setlocal
set "APP_ROOT=%~dp0"
set "MANGO_APP_ROOT=%APP_ROOT%"
start "" /D "%APP_ROOT%" "%APP_ROOT%runtime\pythonw.exe" -m app.main
"@ | Set-Content (Join-Path $Package "Start.bat") -Encoding ASCII
New-Item (Join-Path $Package "data"), (Join-Path $Package "logs"), (Join-Path $Package "downloads") -ItemType Directory | Out-Null

Write-Host "Validating embedded runtime imports..."
$EmbeddedPython = Join-Path $Runtime "python.exe"
& $EmbeddedPython -c "import PySide6; import requests"
if ($LASTEXITCODE -ne 0) { throw "Runtime dependency import check failed with exit code $LASTEXITCODE" }
& $EmbeddedPython -c "import app; import app.main; assert app.__version__ == '0.2.0'"
if ($LASTEXITCODE -ne 0) { throw "Application import check failed with exit code $LASTEXITCODE" }
$PreviousAppRoot = $env:MANGO_APP_ROOT
try {
    $env:MANGO_APP_ROOT = $Package
    & $EmbeddedPython -c "import os; from pathlib import Path; from app.core.paths import AppPaths; assert AppPaths.discover().root == Path(os.environ['MANGO_APP_ROOT']).resolve()"
    if ($LASTEXITCODE -ne 0) { throw "Portable application root check failed with exit code $LASTEXITCODE" }
} finally {
    $env:MANGO_APP_ROOT = $PreviousAppRoot
}

@"
MANGO Downloader 0.2.0

Распакуйте архив полностью и запустите Start.bat.
Python и установка зависимостей не требуются.
Настройки: data\settings.json
Лог: logs\app.log
Записи по умолчанию: downloads\
"@ | Set-Content (Join-Path $Package "README.txt") -Encoding UTF8

$Zip = Join-Path $Dist "MangoDownloader-portable.zip"
Remove-Item $Zip -Force -ErrorAction SilentlyContinue
Write-Host "Creating portable ZIP..."
Compress-Archive (Join-Path $Package "*") $Zip -CompressionLevel Optimal
Write-Host "Portable package created: $Zip"
