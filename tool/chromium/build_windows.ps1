param(
    [Parameter(Mandatory = $true)][string]$Workspace,
    [ValidateRange(1, 4)][int]$Jobs = 3,
    [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'
$nativeArguments = @((Join-Path $PSScriptRoot 'build_windows.py'), '--workspace', $Workspace, '--jobs', "$Jobs")
if ($PrepareOnly) { $nativeArguments += '--prepare-only' }
& python @nativeArguments
if ($LASTEXITCODE -ne 0) { throw "Native Chromium builder failed ($LASTEXITCODE)." }
