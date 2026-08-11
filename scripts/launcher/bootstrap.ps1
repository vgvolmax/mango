param([switch]$Smoke)

$ErrorActionPreference = "Stop"
$ContractVersion = 1
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Runtime = Join-Path $Root "runtime"
$Work = Join-Path $Root ".launcher"
$Downloads = Join-Path $Work "downloads"
$LogDir = Join-Path $Root "logs"
$Log = Join-Path $LogDir "launcher.log"
$ManifestPath = Join-Path $PSScriptRoot "runtime-manifest.json"
$Requirements = Join-Path $Root "requirements\runtime-win-x64.lock.txt"
$Stage = "initialization"

function Write-LauncherLog([string]$Operation, [string]$Message) {
    $safe = ($Message -replace "[\r\n]+", " ")
    Add-Content -LiteralPath $Log -Encoding UTF8 -Value ("{0:o} stage={1} operation={2} {3}" -f (Get-Date), $Stage, $Operation, $safe)
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-Hash([string]$Path, [string]$Expected) {
    $actual = Get-Sha256 $Path
    if ($actual -ne $Expected.ToLowerInvariant()) { throw "SHA-256 verification failed for $(Split-Path $Path -Leaf)." }
}

function Get-Manifest {
    $raw = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    $top = @($raw.PSObject.Properties.Name)
    if ($top.Count -ne 3 -or @($top | Where-Object { $_ -notin @("schema_version", "python", "pip") }).Count) { throw "Runtime manifest has unknown fields." }
    if ($raw.schema_version -ne 1) { throw "Unsupported runtime manifest schema." }
    foreach ($name in @("python", "pip")) {
        $item = $raw.$name; $fields = @($item.PSObject.Properties.Name)
        if ($fields.Count -ne 3 -or @($fields | Where-Object { $_ -notin @("version", "url", "sha256") }).Count) { throw "Runtime manifest $name fields are invalid." }
        if ($item.url -notmatch '^https://[^\s]+$' -or $item.sha256 -notmatch '^[0-9a-fA-F]{64}$' -or $item.version -notmatch '^\d+\.\d+(\.\d+)?$') { throw "Runtime manifest $name value is unsafe or malformed." }
    }
    return $raw
}

function Get-ExpectedState($Manifest) {
    return [ordered]@{ schema_version = 1; python_version = $Manifest.python.version; python_archive_sha256 = $Manifest.python.sha256.ToLowerInvariant(); requirements_sha256 = Get-Sha256 $Requirements; launcher_contract_version = $ContractVersion }
}

function Test-State($Expected) {
    try {
        $state = Get-Content -LiteralPath (Join-Path $Runtime "install-state.json") -Raw | ConvertFrom-Json
        foreach ($key in $Expected.Keys) { if ($state.$key -ne $Expected[$key]) { return $false } }
        return @($state.PSObject.Properties.Name).Count -eq $Expected.Count
    } catch { return $false }
}

function Test-Runtime($Expected) {
    if (!(Test-State $Expected)) { Write-LauncherLog "validation" "state invalid"; return $false }
    $python = Join-Path $Runtime "python.exe"
    if (!(Test-Path -LiteralPath $python -PathType Leaf)) { return $false }
    $env:MANGO_APP_ROOT = $Root
    $code = "import sys,app,app.main,PySide6,requests; assert '.'.join(map(str,sys.version_info[:3]))=='$($Expected.python_version)'; assert app.__version__=='0.2.0'"
    & $python -c $code 2>$null
    $ok = $LASTEXITCODE -eq 0
    Write-LauncherLog "validation" "runtime valid=$ok"
    return $ok
}

function Get-VerifiedDownload([string]$Url, [string]$Hash, [string]$Name) {
    $target = Join-Path $Downloads $Name
    if (Test-Path -LiteralPath $target) { try { Assert-Hash $target $Hash; return $target } catch { Remove-Item -LiteralPath $target -Force } }
    $part = "$target.part"
    Remove-Item -LiteralPath $part -Force -ErrorAction SilentlyContinue
    Write-LauncherLog "download" $Name
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $part
    Assert-Hash $part $Hash
    Move-Item -LiteralPath $part -Destination $target
    return $target
}

function Set-EmbeddedPath([string]$Directory) {
    $pth = Get-ChildItem -LiteralPath $Directory -Filter "python*._pth" | Select-Object -First 1
    if (!$pth) { throw "Embedded Python path configuration is missing." }
    $zip = "python$((Get-Manifest).python.version.Replace('.', '').Substring(0,3)).zip"
    @($zip, ".", "Lib", "Lib\site-packages", "..", "import site") | Set-Content -LiteralPath $pth.FullName -Encoding ASCII
}

function Install-Runtime($Manifest, $Expected) {
    $unique = [Guid]::NewGuid().ToString("N")
    $new = Join-Path $Root "runtime.new-$unique"
    $old = Join-Path $Root "runtime.old-$unique"
    try {
        $archive = Get-VerifiedDownload $Manifest.python.url $Manifest.python.sha256 "python-$($Manifest.python.version)-embed-amd64.zip"
        $pip = Get-VerifiedDownload $Manifest.pip.url $Manifest.pip.sha256 "pip-$($Manifest.pip.version).pyz"
        Expand-Archive -LiteralPath $archive -DestinationPath $new
        New-Item (Join-Path $new "Lib\site-packages") -ItemType Directory -Force | Out-Null
        Set-EmbeddedPath $new
        $python = Join-Path $new "python.exe"
        & $python $pip install --disable-pip-version-check --only-binary=:all: --no-cache-dir --no-compile --target (Join-Path $new "Lib\site-packages") -r $Requirements
        if ($LASTEXITCODE -ne 0) { throw "Runtime dependency installation failed ($LASTEXITCODE)." }
        $Expected | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $new "install-state.json") -Encoding UTF8
        $env:MANGO_APP_ROOT = $Root
        & $python -c "import sys,app,app.main,PySide6,requests; assert '.'.join(map(str,sys.version_info[:3]))=='$($Manifest.python.version)'; assert app.__version__=='0.2.0'"
        if ($LASTEXITCODE -ne 0) { throw "Prepared runtime failed validation." }
        if (Test-Path $Runtime) { Move-Item -LiteralPath $Runtime -Destination $old }
        try { Move-Item -LiteralPath $new -Destination $Runtime } catch { if (Test-Path $old) { Move-Item $old $Runtime }; throw }
        Remove-Item -LiteralPath $old -Recurse -Force -ErrorAction SilentlyContinue
    } finally { Remove-Item -LiteralPath $new -Recurse -Force -ErrorAction SilentlyContinue }
}

try {
    New-Item $LogDir, $Work, $Downloads -ItemType Directory -Force | Out-Null
    $Stage = "environment"; Write-Host "[1/4] Проверка среды"
    if (![Environment]::Is64BitOperatingSystem) { throw "Поддерживается только Windows 10/11 x64." }
    $probe = Join-Path $Root (".write-probe-" + [Guid]::NewGuid())
    try { [IO.File]::WriteAllText($probe, "probe"); Remove-Item $probe -Force } catch { throw "MANGO Downloader не может записывать данные в эту папку. Переместите папку в Рабочий стол, Документы или Загрузки. Запуск от имени администратора не требуется и не рекомендуется." }
    if ((Get-PSDrive -Name ([IO.Path]::GetPathRoot($Root).Substring(0,1))).Free -lt 1GB) { throw "Для подготовки приложения требуется не менее 1 ГБ свободного места." }
    $manifest = Get-Manifest; $expected = Get-ExpectedState $manifest
    $Stage = "runtime"; Write-Host "[2/4] Portable Python"
    New-Item -LiteralPath (Join-Path $Work "launcher.lock") -ItemType File -Force | Out-Null
    $lock = [IO.File]::Open((Join-Path $Work "launcher.lock"), 'Open', 'ReadWrite', 'None')
    try { if (!(Test-Runtime $expected)) { Install-Runtime $manifest $expected } } finally { $lock.Dispose() }
    if (!(Test-Runtime $expected)) { throw "Portable runtime validation failed after preparation." }
    $Stage = "components"; Write-Host "[3/4] Компоненты приложения: готовы"
    $env:MANGO_APP_ROOT = $Root
    if ($Smoke) {
        $Stage = "launch"; Write-Host "[4/4] Проверка запуска MANGO Downloader"
        $env:QT_QPA_PLATFORM = "offscreen"
        & (Join-Path $Runtime "python.exe") -c "from PySide6.QtWidgets import QApplication; from app.core.paths import AppPaths; from app.core.settings import SettingsStore; from app.ui.main_window import MainWindow; import logging; q=QApplication([]); p=AppPaths.discover(); p.ensure_directories(); w=MainWindow(p, SettingsStore(p.settings_file, logging.getLogger('smoke'))); w.close(); print('launcher smoke: OK')"
        if ($LASTEXITCODE -ne 0) { throw "GUI smoke test failed ($LASTEXITCODE)." }
    } else {
        $Stage = "launch"; Write-Host "[4/4] Запуск MANGO Downloader"
        Start-Process -WorkingDirectory $Root -FilePath (Join-Path $Runtime "pythonw.exe") -ArgumentList "-m", "app.main"
    }
    Write-LauncherLog "exit" "exit_code=0"
    exit 0
} catch {
    try { Write-LauncherLog "error" ("{0}; exit_code=1" -f $_.Exception.Message) } catch {}
    Write-Host ""; Write-Host "Не удалось запустить MANGO Downloader." -ForegroundColor Red
    Write-Host "Этап: $Stage"; Write-Host $_.Exception.Message
    Write-Host "Повторите запуск Start.bat. Сохранённые данные не удалены."
    Write-Host "Лог: $Log"
    exit 1
}
