[CmdletBinding()]
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$LauncherArgs)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$runtime = Join-Path $root '.runtime'
$downloads = Join-Path $runtime 'downloads'
$logDir = Join-Path $runtime 'logs'
$logPath = Join-Path $logDir 'launcher.log'
$lockStream = $null

function Write-Log([string]$Stage, [string]$Operation, [string]$Message) {
    $line = "{0:o} stage={1} operation={2} {3}" -f (Get-Date), $Stage, $Operation, $Message
    Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
}
function Get-Hash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Test-Artifact([string]$Path, [string]$Hash) { (Test-Path -LiteralPath $Path -PathType Leaf) -and ((Get-Hash $Path) -eq $Hash) }
function Assert-Uri([uri]$Uri, [string[]]$Hosts) {
    if ($Uri.Scheme -ne 'https' -or $Hosts -notcontains $Uri.DnsSafeHost.ToLowerInvariant()) { throw "Download destination is not allowed: $Uri" }
}
function Receive-Artifact([string]$Url, [string]$Destination, [string]$ExpectedHash, [string[]]$Hosts) {
    if (Test-Artifact $Destination $ExpectedHash) { return }
    $part = "$Destination.part"; Remove-Item -LiteralPath $part -Force -ErrorAction SilentlyContinue
    Add-Type -AssemblyName System.Net.Http
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            $handler = [System.Net.Http.HttpClientHandler]::new(); $handler.AllowAutoRedirect = $false
            $client = [System.Net.Http.HttpClient]::new($handler); $client.Timeout = [TimeSpan]::FromMinutes(10)
            $current = [uri]$Url
            for ($redirect = 0; $redirect -le 5; $redirect++) {
                Assert-Uri $current $Hosts
                $response = $client.GetAsync($current, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
                if ([int]$response.StatusCode -ge 300 -and [int]$response.StatusCode -lt 400) {
                    $location = $response.Headers.Location; $response.Dispose()
                    if ($null -eq $location) { throw 'Redirect has no Location header' }
                    $current = if ($location.IsAbsoluteUri) { $location } else { [uri]::new($current, $location) }
                    continue
                }
                $response.EnsureSuccessStatusCode() | Out-Null
                $input = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
                $output = [IO.File]::Open($part, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None)
                try { $input.CopyTo($output) } finally { $output.Dispose(); $input.Dispose(); $response.Dispose() }
                if ((Get-Hash $part) -ne $ExpectedHash) { throw 'Downloaded file SHA-256 does not match the manifest' }
                [IO.File]::Move($part, $Destination); return
            }
            throw 'Too many redirects'
        } catch {
            Remove-Item -LiteralPath $part -Force -ErrorAction SilentlyContinue
            if ($attempt -eq 3) { throw }
            Start-Sleep -Seconds ([Math]::Pow(2, $attempt))
        } finally {
            if ($null -ne $client) { $client.Dispose() }; if ($null -ne $handler) { $handler.Dispose() }
        }
    }
}
function Test-Python([string]$PythonDir, $PythonSpec) {
    foreach ($name in @('python.exe','pythonw.exe','python3.dll','python313.dll','install-receipt.json')) { if (!(Test-Path (Join-Path $PythonDir $name))) { return $false } }
    try {
        $receipt = Get-Content (Join-Path $PythonDir 'install-receipt.json') -Raw | ConvertFrom-Json
        if ($receipt.schema_version -ne 1 -or $receipt.version -ne $PythonSpec.version -or $receipt.sha256 -ne $PythonSpec.sha256) { return $false }
        $reported = & (Join-Path $PythonDir 'python.exe') -c 'import platform; print(platform.python_version())'
        return ($LASTEXITCODE -eq 0 -and $reported.Trim() -eq $PythonSpec.version)
    } catch { return $false }
}
function Set-EmbeddedPath([string]$PythonDir) {
    $content = @('python313.zip','.','..\site-packages','..\..','import site')
    [IO.File]::WriteAllLines((Join-Path $PythonDir 'python313._pth'), $content, [Text.UTF8Encoding]::new($false))
}
function Install-Python($Spec, [string[]]$Hosts) {
    $archive = Join-Path $downloads 'python.zip'
    Receive-Artifact $Spec.url $archive $Spec.sha256 $Hosts
    $staging = Join-Path $runtime ("python.new-{0}-{1}" -f $PID, [guid]::NewGuid().ToString('N'))
    $old = Join-Path $runtime 'python.old'
    New-Item -ItemType Directory -Path $staging | Out-Null
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zip = [IO.Compression.ZipFile]::OpenRead($archive)
        try {
            $prefix = [IO.Path]::GetFullPath($staging + [IO.Path]::DirectorySeparatorChar)
            foreach ($entry in $zip.Entries) {
                $target = [IO.Path]::GetFullPath((Join-Path $staging $entry.FullName))
                if (!$target.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe path in Python archive' }
            }
        } finally { $zip.Dispose() }
        [IO.Compression.ZipFile]::ExtractToDirectory($archive, $staging)
        Set-EmbeddedPath $staging
        $receipt = [ordered]@{schema_version=1; version=$Spec.version; sha256=$Spec.sha256} | ConvertTo-Json
        [IO.File]::WriteAllText((Join-Path $staging 'install-receipt.json'), $receipt + "`n", [Text.UTF8Encoding]::new($false))
        if (!(Test-Python $staging $Spec)) { throw 'Extracted Python runtime did not pass validation' }
        Remove-Item $old -Recurse -Force -ErrorAction SilentlyContinue
        $active = Join-Path $runtime 'python'; if (Test-Path $active) { Move-Item $active $old }
        try { Move-Item $staging $active } catch { if ((Test-Path $old) -and !(Test-Path $active)) { Move-Item $old $active }; throw }
        Remove-Item $old -Recurse -Force -ErrorAction SilentlyContinue
    } finally { Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue }
}

try {
    New-Item -ItemType Directory -Force -Path $runtime,$downloads,$logDir | Out-Null
    $probe = Join-Path $runtime '.write-test'; [IO.File]::WriteAllText($probe, 'ok'); Remove-Item $probe
    $lockPath = Join-Path $runtime 'launcher.lock'
    $lockStream = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    $metadata = [Text.Encoding]::UTF8.GetBytes((@{pid=$PID; acquired=(Get-Date).ToString('o')} | ConvertTo-Json -Compress))
    $lockStream.SetLength(0); $lockStream.Write($metadata,0,$metadata.Length); $lockStream.Flush()
    $manifest = Get-Content (Join-Path $PSScriptRoot 'runtime-manifest.json') -Raw | ConvertFrom-Json
    Write-Host '[1/4] Portable Python'
    $pythonDir = Join-Path $runtime 'python'
    if (!(Test-Python $pythonDir $manifest.python)) { Write-Log python prepare start; Install-Python $manifest.python $manifest.download_hosts }
    Set-EmbeddedPath $pythonDir
    Write-Host '[1/4] Portable Python: готов'
    $pipPath = Join-Path $downloads ("pip-{0}.pyz" -f $manifest.pip.version)
    Receive-Artifact $manifest.pip.url $pipPath $manifest.pip.sha256 $manifest.download_hosts
    & (Join-Path $pythonDir 'python.exe') (Join-Path $PSScriptRoot 'launcher.py') @LauncherArgs
    $code = $LASTEXITCODE; Write-Log launcher exit "code=$code"; exit $code
} catch [System.UnauthorizedAccessException] {
    Write-Host ''; Write-Host 'MANGO Downloader не может записывать данные в эту папку.'
    Write-Host 'Переместите полностью распакованную папку, например, в: Рабочий стол / Документы / Загрузки.'
    Write-Host 'Запуск от имени администратора не требуется.'; exit 1
} catch {
    if (Test-Path $logDir) { Write-Log bootstrap failure ("type={0} message={1}" -f $_.Exception.GetType().Name, $_.Exception.Message) }
    Write-Host ''; Write-Host 'Не удалось подготовить MANGO Downloader.'; Write-Host 'Уже загруженные корректные компоненты сохранены.'
    Write-Host 'Повторите запуск; незавершённый этап будет выполнен снова.'; Write-Host "Подробности: $logPath"; exit 1
} finally { if ($null -ne $lockStream) { $lockStream.Dispose() } }
