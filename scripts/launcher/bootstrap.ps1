$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$RuntimeSmoke = $args -contains '--runtime-smoke'

Add-Type -AssemblyName System.Net.Http
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$RuntimeDir = Join-Path $Root '.runtime'
$PythonDir = Join-Path $RuntimeDir 'python'
$DownloadsDir = Join-Path $RuntimeDir 'downloads'
$ArchivePath = Join-Path $DownloadsDir 'python.zip'
$PipDir = Join-Path $RuntimeDir 'pip'
$LockPath = Join-Path $RuntimeDir 'launcher.lock'
$ManifestPath = Join-Path $PSScriptRoot 'runtime-manifest.json'
$ReceiptName = 'install-receipt.json'

function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $algorithm.Dispose()
        $stream.Dispose()
    }
}

function Assert-AllowedUri([Uri]$Uri, [string[]]$AllowedHosts) {
    if ($Uri.Scheme -ne [Uri]::UriSchemeHttps) {
        throw "Download URI must use HTTPS: $Uri"
    }
    if ($AllowedHosts -notcontains $Uri.DnsSafeHost) {
        throw "Download host is not allowed: $($Uri.DnsSafeHost)"
    }
}

function Test-PortablePython([string]$Directory, $PythonSpec) {
    foreach ($name in @('python.exe', 'pythonw.exe', 'python3.dll', 'python313.dll', $ReceiptName)) {
        if (-not [IO.File]::Exists((Join-Path $Directory $name))) { return $false }
    }

    try {
        $receipt = Get-Content -LiteralPath (Join-Path $Directory $ReceiptName) -Raw | ConvertFrom-Json
        if ([int]$receipt.schema_version -ne 1 -or
            [string]$receipt.version -cne [string]$PythonSpec.version -or
            [string]$receipt.sha256 -cne [string]$PythonSpec.sha256) {
            return $false
        }

        $version = & (Join-Path $Directory 'python.exe') -c 'import platform; print(platform.python_version())'
        return ($LASTEXITCODE -eq 0 -and (($version | Out-String).Trim() -ceq [string]$PythonSpec.version))
    }
    catch {
        return $false
    }
}

function Invoke-StreamingDownload([Uri]$InitialUri, [string]$Destination, [string[]]$AllowedHosts) {
    $handler = New-Object System.Net.Http.HttpClientHandler
    $handler.AllowAutoRedirect = $false
    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(60)
    $cancellation = New-Object System.Threading.CancellationTokenSource
    $cancellation.CancelAfter([TimeSpan]::FromMinutes(5))
    try {
        $uri = $InitialUri
        for ($redirects = 0; $redirects -le 10; $redirects++) {
            Assert-AllowedUri $uri $AllowedHosts
            $response = $null
            try {
                $response = $client.GetAsync(
                    $uri,
                    [Net.Http.HttpCompletionOption]::ResponseHeadersRead,
                    $cancellation.Token
                ).GetAwaiter().GetResult()

                if ([int]$response.StatusCode -in @(301, 302, 303, 307, 308)) {
                    if ($redirects -eq 10) { throw 'Too many download redirects.' }
                    if ($null -eq $response.Headers.Location) { throw 'Redirect response has no Location header.' }
                    $uri = [Uri]::new($uri, $response.Headers.Location)
                    Assert-AllowedUri $uri $AllowedHosts
                    continue
                }

                $response.EnsureSuccessStatusCode() | Out-Null
                Assert-AllowedUri $response.RequestMessage.RequestUri $AllowedHosts
                $expected = $response.Content.Headers.ContentLength
                $input = $null
                $output = $null
                try {
                    $input = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
                    $output = New-Object IO.FileStream(
                        $Destination,
                        [IO.FileMode]::Create,
                        [IO.FileAccess]::Write,
                        [IO.FileShare]::None
                    )
                    $buffer = New-Object byte[] (256 * 1024)
                    [long]$received = 0
                    while (($count = $input.ReadAsync(
                        $buffer,
                        0,
                        $buffer.Length,
                        $cancellation.Token
                    ).GetAwaiter().GetResult()) -gt 0) {
                        $output.Write($buffer, 0, $count)
                        $received += $count
                    }
                }
                finally {
                    if ($null -ne $output) { $output.Dispose() }
                    if ($null -ne $input) { $input.Dispose() }
                }
                if ($null -ne $expected -and $received -ne $expected) {
                    throw [IO.IOException]::new("Incomplete download: received $received of $expected bytes.")
                }
                return
            }
            finally {
                if ($null -ne $response) { $response.Dispose() }
            }
        }
    }
    finally {
        $cancellation.Dispose()
        $client.Dispose()
        $handler.Dispose()
    }
}

function Save-VerifiedArchive($PythonSpec, [string[]]$AllowedHosts) {
    if ([IO.File]::Exists($ArchivePath)) {
        if ((Get-Sha256 $ArchivePath) -ceq [string]$PythonSpec.sha256) { return }
        Remove-Item -LiteralPath $ArchivePath -Force
    }

    $partPath = "$ArchivePath.part"
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        Remove-Item -LiteralPath $partPath -Force -ErrorAction SilentlyContinue
        try {
            Invoke-StreamingDownload ([Uri]$PythonSpec.url) $partPath $AllowedHosts
            if ((Get-Sha256 $partPath) -cne [string]$PythonSpec.sha256) {
                throw 'Downloaded Python archive SHA-256 does not match the manifest.'
            }
            Move-Item -LiteralPath $partPath -Destination $ArchivePath -Force
            return
        }
        catch [Net.Http.HttpRequestException], [Threading.Tasks.TaskCanceledException], [IO.IOException] {
            Remove-Item -LiteralPath $partPath -Force -ErrorAction SilentlyContinue
            if ($attempt -eq 3) { throw }
            Start-Sleep -Seconds 2
        }
        catch {
            Remove-Item -LiteralPath $partPath -Force -ErrorAction SilentlyContinue
            throw
        }
    }
}

function Expand-SafeArchive([string]$Archive, [string]$Destination) {
    [IO.Directory]::CreateDirectory($Destination) | Out-Null
    $stagingRoot = [IO.Path]::GetFullPath($Destination).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        foreach ($entry in $zip.Entries) {
            $entryPath = [IO.Path]::GetFullPath((Join-Path $Destination $entry.FullName))
            if (-not $entryPath.StartsWith($stagingRoot, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Unsafe ZIP entry path: $($entry.FullName)"
            }
        }
    }
    finally {
        $zip.Dispose()
    }
    [IO.Compression.ZipFile]::ExtractToDirectory($Archive, $Destination)
}

function Install-PortablePython($PythonSpec, [string[]]$AllowedHosts) {
    Get-ChildItem -LiteralPath $RuntimeDir -Directory -Filter 'python.new-*' -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force
    Save-VerifiedArchive $PythonSpec $AllowedHosts

    $staging = Join-Path $RuntimeDir ("python.new-{0}-{1}" -f $PID, [Guid]::NewGuid().ToString('N'))
    $old = Join-Path $RuntimeDir ("python.old-{0}" -f $PID)
    try {
        Expand-SafeArchive $ArchivePath $staging
        [ordered]@{
            schema_version = 1
            version = [string]$PythonSpec.version
            sha256 = [string]$PythonSpec.sha256
        } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $staging $ReceiptName) -Encoding UTF8

        if (-not (Test-PortablePython $staging $PythonSpec)) {
            throw 'Staged portable Python failed validation.'
        }

        $hadActive = [IO.Directory]::Exists($PythonDir)
        if ($hadActive) { Move-Item -LiteralPath $PythonDir -Destination $old }
        try {
            Move-Item -LiteralPath $staging -Destination $PythonDir
        }
        catch {
            if ($hadActive -and -not [IO.Directory]::Exists($PythonDir)) {
                Move-Item -LiteralPath $old -Destination $PythonDir
            }
            throw
        }
        if ([IO.Directory]::Exists($old)) { Remove-Item -LiteralPath $old -Recurse -Force }
    }
    finally {
        if ([IO.Directory]::Exists($staging)) { Remove-Item -LiteralPath $staging -Recurse -Force }
    }
}

function Test-PipTool([string]$Directory, $PipSpec) {
    $receiptPath = Join-Path $Directory $ReceiptName
    if (-not [IO.File]::Exists($receiptPath)) { return $false }
    try {
        $receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
        if ([int]$receipt.schema_version -ne 1 -or
            [string]$receipt.version -cne [string]$PipSpec.version -or
            [string]$receipt.sha256 -cne [string]$PipSpec.sha256) { return $false }
        $escaped = $Directory.Replace("'", "''")
        & (Join-Path $PythonDir 'python.exe') -c "import sys; sys.path.insert(0, r'$escaped'); import pip; assert pip.__version__ == '24.3.1'"
        return $LASTEXITCODE -eq 0
    }
    catch { return $false }
}

function Install-PipTool($PipSpec, [string[]]$AllowedHosts) {
    $wheelName = "pip-$($PipSpec.version)-py3-none-any.whl"
    $wheelPath = Join-Path $DownloadsDir $wheelName
    if ([IO.File]::Exists($wheelPath) -and (Get-Sha256 $wheelPath) -cne [string]$PipSpec.sha256) {
        Remove-Item -LiteralPath $wheelPath -Force
    }
    if (-not [IO.File]::Exists($wheelPath)) {
        $partPath = "$wheelPath.part"
        for ($attempt = 1; $attempt -le 3; $attempt++) {
            Remove-Item -LiteralPath $partPath -Force -ErrorAction SilentlyContinue
            try {
                Invoke-StreamingDownload ([Uri]$PipSpec.url) $partPath $AllowedHosts
                if ((Get-Sha256 $partPath) -cne [string]$PipSpec.sha256) { throw 'Downloaded pip wheel SHA-256 does not match the manifest.' }
                Move-Item -LiteralPath $partPath -Destination $wheelPath -Force
                break
            }
            catch [Net.Http.HttpRequestException], [Threading.Tasks.TaskCanceledException], [IO.IOException] {
                Remove-Item -LiteralPath $partPath -Force -ErrorAction SilentlyContinue
                if ($attempt -eq 3) { throw }
                Start-Sleep -Seconds 2
            }
        }
    }

    Get-ChildItem -LiteralPath $RuntimeDir -Directory -Filter 'pip.new-*' -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
    $staging = Join-Path $RuntimeDir ("pip.new-{0}-{1}" -f $PID, [Guid]::NewGuid().ToString('N'))
    $old = Join-Path $RuntimeDir ("pip.old-{0}" -f $PID)
    try {
        $zip = [IO.Compression.ZipFile]::OpenRead($wheelPath)
        try {
            foreach ($entry in $zip.Entries) {
                if ($entry.FullName -match '(^|/)[^/]+\.data/') { throw 'Pinned pip wheel unexpectedly contains a .data layout.' }
            }
        }
        finally { $zip.Dispose() }
        Expand-SafeArchive $wheelPath $staging
        [ordered]@{ schema_version = 1; version = [string]$PipSpec.version; sha256 = [string]$PipSpec.sha256 } |
            ConvertTo-Json | Set-Content -LiteralPath (Join-Path $staging $ReceiptName) -Encoding UTF8
        if (-not (Test-PipTool $staging $PipSpec)) { throw 'Staged pip tool failed validation.' }
        $hadActive = [IO.Directory]::Exists($PipDir)
        if ($hadActive) { Move-Item -LiteralPath $PipDir -Destination $old }
        try { Move-Item -LiteralPath $staging -Destination $PipDir }
        catch {
            if ($hadActive -and -not [IO.Directory]::Exists($PipDir)) { Move-Item -LiteralPath $old -Destination $PipDir }
            throw
        }
        if ([IO.Directory]::Exists($old)) { Remove-Item -LiteralPath $old -Recurse -Force }
    }
    finally { if ([IO.Directory]::Exists($staging)) { Remove-Item -LiteralPath $staging -Recurse -Force } }
}

function Set-ApplicationPythonPaths {
    $path = Join-Path $PythonDir 'python313._pth'
    $temporary = "$path.new"
    $canonical = "python313.zip`r`n.`r`n..\pip`r`n..\site-packages`r`n..\..`r`n"
    [IO.File]::WriteAllText($temporary, $canonical, [Text.UTF8Encoding]::new($false))
    if ([IO.File]::ReadAllText($temporary) -cne $canonical) { throw 'Embedded Python path validation failed.' }
    if (-not [IO.File]::Exists($path) -or [IO.File]::ReadAllText($path) -cne $canonical) {
        if ([IO.File]::Exists($path)) {
            $backup = "$path.backup-$PID-$([Guid]::NewGuid().ToString('N'))"
            [IO.File]::Replace($temporary, $path, $backup)
            [IO.File]::Delete($backup)
        }
        else { [IO.File]::Move($temporary, $path) }
    }
    else { Remove-Item -LiteralPath $temporary -Force }
}

[IO.Directory]::CreateDirectory($RuntimeDir) | Out-Null
[IO.Directory]::CreateDirectory($DownloadsDir) | Out-Null
$Lock = [IO.File]::Open(
    $LockPath,
    [IO.FileMode]::OpenOrCreate,
    [IO.FileAccess]::ReadWrite,
    [IO.FileShare]::ReadWrite
)
$lockHeld = $false
try {
    $deadline = [DateTime]::UtcNow.AddMinutes(20)
    while (-not $lockHeld) {
        try {
            $Lock.Lock(0,1)
            $lockHeld = $true
        }
        catch [IO.IOException] {
            if ([DateTime]::UtcNow -ge $deadline) { throw 'Timed out waiting for another bootstrap process.' }
            Start-Sleep -Milliseconds 500
        }
    }

    $manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    if ([int]$manifest.schema_version -ne 1 -or $null -eq $manifest.python -or $null -eq $manifest.pip -or
        [string]::IsNullOrWhiteSpace([string]$manifest.python.version) -or
        [string]::IsNullOrWhiteSpace([string]$manifest.python.url) -or
        [string]$manifest.python.sha256 -notmatch '^[0-9a-f]{64}$' -or
        [string]$manifest.python.executable -cne 'python.exe' -or
        [string]$manifest.pip.version -cne '24.3.1' -or
        [string]::IsNullOrWhiteSpace([string]$manifest.pip.url) -or
        [string]$manifest.pip.sha256 -notmatch '^[0-9a-f]{64}$') {
        throw 'Invalid runtime manifest.'
    }

    Write-Host '[1/3] Preparing portable Python...'
    if (-not (Test-PortablePython $PythonDir $manifest.python)) {
        Install-PortablePython $manifest.python ([string[]]$manifest.download_hosts)
    }
    if (-not (Test-PortablePython $PythonDir $manifest.python)) {
        throw 'Portable Python runtime validation failed.'
    }
    Write-Host 'Portable Python: verified and ready'

    if ($RuntimeSmoke) {
        & (Join-Path $PythonDir 'python.exe') -c "import platform; assert platform.python_version() == '3.13.7'"
        if ($LASTEXITCODE -ne 0) { throw 'Portable Python runtime smoke failed.' }
    }
    else {
        Write-Host '[2/3] Preparing pinned pip tool...'
        if (-not (Test-PipTool $PipDir $manifest.pip)) {
            Install-PipTool $manifest.pip ([string[]]$manifest.download_hosts)
        }
        if (-not (Test-PipTool $PipDir $manifest.pip)) { throw 'Pinned pip tool validation failed.' }
        Set-ApplicationPythonPaths
        Write-Host 'pip 24.3.1: verified and ready'
        Write-Host '[3/3] Preparing application...'
        $mode = if ($args -contains '--smoke') { '--smoke' } else { 'start' }
        & (Join-Path $PythonDir 'python.exe') (Join-Path $PSScriptRoot 'launcher.py') $mode
        if ($LASTEXITCODE -ne 0) { throw 'Application launcher failed. See .runtime\logs\launcher.log.' }
    }
}
catch {
    Write-Error $_
    exit 1
}
finally {
    if ($lockHeld) { $Lock.Unlock(0,1) }
    $Lock.Dispose()
}

exit 0
