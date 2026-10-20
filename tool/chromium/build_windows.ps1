param(
    [Parameter(Mandatory = $true)][string]$Workspace,
    [ValidateRange(1, 4)][int]$Jobs = 3,
    [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$product = Get-Content (Join-Path $projectRoot 'native\chromium\product.json') -Raw | ConvertFrom-Json
$overlayPython = (Get-Command python -ErrorAction Stop).Source
$workspacePath = [IO.Path]::GetFullPath($Workspace)
if ($workspacePath -match '\s') { throw 'Chromium workspace path must not contain spaces.' }
New-Item -ItemType Directory -Path $workspacePath -Force | Out-Null
$workspaceLock = [IO.File]::Open((Join-Path $workspacePath '.internet-browser-build.lock'),
    [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
try {
if ((Get-PSDrive -Name ([IO.Path]::GetPathRoot($workspacePath).TrimEnd(':\'))).Free -lt 120GB) {
    throw 'Native Chromium requires at least 120 GiB of free workspace disk.'
}

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed ($LASTEXITCODE)." }
}

$depot = Join-Path $workspacePath 'depot_tools'
$source = Join-Path $workspacePath 'src'
if (-not (Test-Path (Join-Path $depot '.git'))) {
    Invoke-Checked 'git' @('clone', $product.depot_tools_repository, $depot)
}
Invoke-Checked 'git' @('-C', $depot, 'fetch', '--depth', '1', 'origin', $product.depot_tools_revision)
Invoke-Checked 'git' @('-C', $depot, 'checkout', '--detach', $product.depot_tools_revision)
$env:PATH = "$depot;$env:PATH"
$env:DEPOT_TOOLS_WIN_TOOLCHAIN = '0'
$env:DEPOT_TOOLS_UPDATE = '0'
$env:DEPOT_TOOLS_METRICS = '0'
# These values are process-scoped; no global Git or machine settings change.
$env:GIT_CONFIG_COUNT = '2'
$env:GIT_CONFIG_KEY_0 = 'core.longpaths'
$env:GIT_CONFIG_VALUE_0 = 'true'
$env:GIT_CONFIG_KEY_1 = 'core.autocrlf'
$env:GIT_CONFIG_VALUE_1 = 'false'
if (-not (Test-Path (Join-Path $source '.git'))) {
    Invoke-Checked 'git' @('clone', '--depth', '1', '--branch', $product.chromium_version,
        '--single-branch', $product.chromium_repository, $source)
}
$actualRevision = (& git -C $source rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $actualRevision -ne $product.chromium_revision) {
    throw 'Chromium source revision differs from the reviewed product pin.'
}
$client = Join-Path $workspacePath '.gclient'
$clientText = "solutions = [{`"name`": `"src`", `"url`": `"$($product.chromium_repository)`", `"managed`": False, `"custom_deps`": {}, `"custom_vars`": {}}]`ntarget_os = [`"win`"]`n"
if ((Test-Path $client) -and (Get-Content $client -Raw).Trim() -ne $clientText.Trim()) {
    throw 'Existing .gclient differs from native Windows configuration.'
}
[IO.File]::WriteAllText($client, $clientText)
Push-Location $workspacePath
try {
    # gclient rejects tracked source edits. Preserve any unknown edits and
    # remove only our exact recorded overlay before synchronizing.
    Invoke-Checked $overlayPython @((Join-Path $PSScriptRoot 'prepare_windows.py'), '--checkout', $source, '--remove')
    Invoke-Checked (Join-Path $depot 'gclient.bat') @('sync', '--no-history', '--nohooks', '-j', '2',
        '--revision', "src@$($product.chromium_revision)")
    if ($PrepareOnly) {
        Write-Output 'Pinned Windows source and dependencies prepared; no native compilation performed.'
        return
    }
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    $vs = & $vswhere -latest -products '*' -version '[18.0,19.0)' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (-not $vs) { throw 'Visual Studio 2026 with Desktop C++ and ATL/MFC is required.' }
    $env:vs2026_install = $vs.Trim()
    Invoke-Checked (Join-Path $depot 'gclient.bat') @('runhooks')
    # Use the caller's Python with Pillow, rather than depot_tools' vpython.
    Invoke-Checked $overlayPython @((Join-Path $PSScriptRoot 'prepare_windows.py'), '--checkout', $source)
    $out = Join-Path $source 'out\InternetBrowser'
    New-Item -ItemType Directory -Path $out -Force | Out-Null
    Copy-Item (Join-Path $projectRoot 'native\chromium\windows\args.gn') (Join-Path $out 'args.gn')
    Push-Location $source
    try {
        Invoke-Checked (Join-Path $depot 'gn.bat') @('gen', 'out\InternetBrowser')
        Invoke-Checked (Join-Path $depot 'autoninja.bat') @('-C', 'out\InternetBrowser', '-j', "$Jobs", 'chrome', 'mini_installer')
    } finally { Pop-Location }
    foreach ($name in @('chrome.exe', 'chrome.7z', 'mini_installer.exe')) {
        if (-not (Test-Path (Join-Path $out $name))) { throw "Missing native build output: $name" }
    }
    $report = @{
        product = $product
        integration_commit = (& git -C $projectRoot rev-parse HEAD).Trim()
        chrome_exe_sha256 = (Get-FileHash (Join-Path $out 'chrome.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
        archive_sha256 = (Get-FileHash (Join-Path $out 'chrome.7z') -Algorithm SHA256).Hash.ToLowerInvariant()
        installer_sha256 = (Get-FileHash (Join-Path $out 'mini_installer.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
        native_source_compiled = $true
        runtime_verified = $false
        release_approved = $false
    }
    $report | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $out 'native-provenance.json') -Encoding utf8
    Write-Output "Native Chromium built at $out. Integration and extension runtime checks remain required."
} finally { Pop-Location }
} finally { $workspaceLock.Dispose() }
