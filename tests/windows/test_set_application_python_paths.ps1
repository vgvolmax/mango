$ErrorActionPreference = 'Stop'

$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$bootstrapPath = Join-Path $root 'scripts\launcher\bootstrap.ps1'
$tokens = $null
$parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile(
    $bootstrapPath,
    [ref]$tokens,
    [ref]$parseErrors
)
if ($parseErrors.Count -ne 0) { throw 'bootstrap.ps1 did not parse successfully.' }

$functionAst = $ast.Find(
    { param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -ceq 'Set-ApplicationPythonPaths' },
    $true
)
if ($null -eq $functionAst) { throw 'Set-ApplicationPythonPaths was not found.' }
Invoke-Expression $functionAst.Extent.Text

$script:PythonDir = Join-Path ([IO.Path]::GetTempPath()) ("MANGO path тест-{0}" -f [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($script:PythonDir) | Out-Null
$path = Join-Path $script:PythonDir 'python313._pth'
$canonical = "python313.zip`r`n.`r`n..\pip`r`n..\site-packages`r`n..\..`r`n"

try {
    # A fresh embedded runtime publishes the temporary file without File.Replace.
    Set-ApplicationPythonPaths
    if ([IO.File]::ReadAllText($path) -cne $canonical) { throw 'Fresh path file is not canonical.' }
    if ([IO.File]::Exists("$path.new")) { throw 'Fresh publication left its temporary file behind.' }

    # An existing path file uses File.Replace with a real backup, then removes it.
    [IO.File]::WriteAllText($path, "obsolete`r`n", [Text.UTF8Encoding]::new($false))
    Set-ApplicationPythonPaths
    if ([IO.File]::ReadAllText($path) -cne $canonical) { throw 'Existing path file was not replaced.' }
    if ([IO.File]::Exists("$path.new")) { throw 'Replacement left its temporary file behind.' }
    if (Get-ChildItem -LiteralPath $script:PythonDir -Filter 'python313._pth.backup-*') {
        throw 'Successful replacement left its backup file behind.'
    }

    # An already canonical file remains intact and does not leave publication artifacts.
    Set-ApplicationPythonPaths
    if ([IO.File]::ReadAllText($path) -cne $canonical) { throw 'Canonical path file was changed.' }
    if ([IO.File]::Exists("$path.new")) { throw 'Canonical path validation left its temporary file behind.' }
}
finally {
    Remove-Item -LiteralPath $script:PythonDir -Recurse -Force -ErrorAction SilentlyContinue
}
