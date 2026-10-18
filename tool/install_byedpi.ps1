# Bundle a fixed, SHA-256 verified upstream ByeDPI Windows build.
$ErrorActionPreference = 'Stop'
$version = '0.17.3'
$archive = 'byedpi-17.3-x86_64-w64.zip'
$expectedSha = '70d2c94147193cb915f9c6eb5144b8d404dacbcfa90bda2383b6b211afafa456'
$uri = "https://github.com/hufrea/byedpi/releases/download/v$version/$archive"
$work = Join-Path $env:RUNNER_TEMP 'browser-byedpi'
New-Item -ItemType Directory -Path $work -Force | Out-Null
$zip = Join-Path $work $archive
Invoke-WebRequest -Uri $uri -OutFile $zip -MaximumRedirection 5
$actual = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expectedSha) {
    throw 'ByeDPI archive SHA-256 mismatch. Refusing to package binary.'
}
$unzipped = Join-Path $work 'payload'
Expand-Archive -LiteralPath $zip -DestinationPath $unzipped -Force
$bin = Get-ChildItem -Path $unzipped -Recurse -Filter ciadpi.exe -File | Select-Object -First 1
if (-not $bin) { throw 'Upstream archive did not contain ciadpi.exe.' }
$target = 'build/windows/x64/runner/Release/tools'
New-Item -ItemType Directory -Path $target -Force | Out-Null
Copy-Item $bin.FullName (Join-Path $target 'ciadpi.exe') -Force
Copy-Item 'third_party/byedpi/LICENSE' (Join-Path $target 'LICENSE-byeDPI.txt') -Force
Write-Host "Bundled checked ByeDPI v$version for Windows."
