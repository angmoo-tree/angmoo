[CmdletBinding()]
param(
    [string]$Python = "",
    [string]$WorkRoot = "",
    [ValidateSet("OneFile", "OneDir")]
    [string]$Layout = "OneFile",
    [switch]$DiagnosticOnly
)

$ErrorActionPreference = "Stop"
$desktopRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$repoRoot = (Resolve-Path (Join-Path $desktopRoot "..")).Path
if (-not $Python) {
    $Python = Join-Path $repoRoot "backend\.venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Pinned backend Python environment is missing: $Python"
}
if (-not $WorkRoot) {
    $WorkRoot = Join-Path $repoRoot ".codex-temp\l3-er5-product-sidecar"
}

$backendRoot = Join-Path $repoRoot "backend"
$entrypoint = Join-Path $backendRoot "app\runtime\desktop_sidecar.py"
$distRoot = Join-Path $WorkRoot "dist"
$buildRoot = Join-Path $WorkRoot "build"
$specRoot = Join-Path $WorkRoot "spec"
$binaryRoot = Join-Path $desktopRoot "src-tauri\binaries"
New-Item -ItemType Directory -Path $distRoot,$buildRoot,$specRoot,$binaryRoot -Force | Out-Null

& $Python -c "import PyInstaller; assert PyInstaller.__version__ == '6.16.0'"
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller 6.16.0 is required in the selected Python environment"
}

$layoutArgument = if ($Layout -eq "OneFile") { "--onefile" } else { "--onedir" }

& $Python -m PyInstaller `
    --clean `
    --noconfirm `
    $layoutArgument `
    --noconsole `
    --noupx `
    --name angmoo-sidecar `
    --paths $backendRoot `
    --collect-all ladybug `
    --hidden-import sqlalchemy.dialects.sqlite `
    --exclude-module psycopg `
    --exclude-module psycopg_binary `
    --exclude-module oci `
    --exclude-module pytest `
    --distpath $distRoot `
    --workpath $buildRoot `
    --specpath $specRoot `
    $entrypoint
if ($LASTEXITCODE -ne 0) { throw "Angmoo product sidecar packaging failed" }

$targetTriple = (& rustc --print host-tuple).Trim()
if (-not $targetTriple) { throw "Rust host target could not be determined" }
$source = if ($Layout -eq "OneFile") {
    Join-Path $distRoot "angmoo-sidecar.exe"
}
else {
    Join-Path $distRoot "angmoo-sidecar\angmoo-sidecar.exe"
}
$sourceDirectory = if ($Layout -eq "OneDir") {
    Join-Path $distRoot "angmoo-sidecar"
}
else {
    $null
}
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Angmoo packaged sidecar output is missing: $source"
}
$target = Join-Path $binaryRoot "angmoo-sidecar-$targetTriple.exe"
$hashTarget = "$target.sha256"
if (-not $DiagnosticOnly) {
    if ($Layout -ne "OneFile") {
        throw "Only the OneFile layout can be copied into Tauri externalBin"
    }
    Copy-Item -LiteralPath $source -Destination $target -Force
}
$packagedBinary = if ($DiagnosticOnly) { $source } else { $target }
$stream = [System.IO.File]::OpenRead($packagedBinary)
try {
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hashBytes = $hasher.ComputeHash($stream)
    }
    finally {
        $hasher.Dispose()
    }
}
finally {
    $stream.Dispose()
}
$hash = [System.BitConverter]::ToString($hashBytes).Replace("-", "").ToLowerInvariant()
if (-not $DiagnosticOnly) {
    Set-Content -LiteralPath $hashTarget -Value $hash -Encoding ascii -NoNewline
}

[ordered]@{
    schema_version = 1
    status = "PASS"
    target = $targetTriple
    layout = $Layout
    diagnostic_only = [bool]$DiagnosticOnly
    sidecar = if ($DiagnosticOnly) { $source } else { $target }
    distribution_directory = $sourceDirectory
    sha256 = $hash
    bytes = (Get-Item -LiteralPath $packagedBinary).Length
} | ConvertTo-Json
