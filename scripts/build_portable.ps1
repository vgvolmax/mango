$ErrorActionPreference = "Stop"
$PythonVersion = "3.12.8"
$Root = Split-Path -Parent $PSScriptRoot
$Dist = Join-Path $Root "dist"
$Package = Join-Path $Dist "MangoDownloader"
$Cache = Join-Path $Root "build"
$PythonZip = Join-Path $Cache "python-$PythonVersion-embed-amd64.zip"
$PythonUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"

Remove-Item $Package -Recurse -Force -ErrorAction SilentlyContinue
New-Item $Cache, $Package -ItemType Directory -Force | Out-Null
if (!(Test-Path $PythonZip)) { Invoke-WebRequest $PythonUrl -OutFile $PythonZip }

$Runtime = Join-Path $Package "runtime"
Expand-Archive $PythonZip $Runtime
$Pth = Get-ChildItem $Runtime -Filter "python*._pth" | Select-Object -First 1
(Get-Content $Pth.FullName) -replace '^#import site$', 'import site' | Set-Content $Pth.FullName -Encoding ASCII
Add-Content $Pth.FullName ".." -Encoding ASCII

$GetPip = Join-Path $Cache "get-pip.py"
Invoke-WebRequest "https://bootstrap.pypa.io/pip/3.12/get-pip.py" -OutFile $GetPip
& (Join-Path $Runtime "python.exe") $GetPip "pip==24.3.1" --no-warn-script-location
& (Join-Path $Runtime "python.exe") -m pip install --no-compile --requirement (Join-Path $Root "requirements\runtime.txt")

Copy-Item (Join-Path $Root "app") $Package -Recurse
Copy-Item (Join-Path $Root "Start.bat") $Package
New-Item (Join-Path $Package "data"), (Join-Path $Package "logs"), (Join-Path $Package "downloads") -ItemType Directory | Out-Null
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
Compress-Archive (Join-Path $Package "*") $Zip -CompressionLevel Optimal
Write-Host "Portable package created: $Zip"
