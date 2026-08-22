[CmdletBinding()]
param(
    [string]$Python = "",
    [string]$WorkRoot = ""
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

& $Python -m PyInstaller `
    --clean `
    --noconfirm `
    --onefile `
    --noconsole `
    --noupx `
    --name angmoo-sidecar `
    --paths $backendRoot `
    --collect-all ladybug `
    --hidden-import sqlalchemy.dialects.sqlite `
    --hidden-import sqlalchemy.dialects.postgresql `
    --hidden-import psycopg `
    --exclude-module oci `
    --exclude-module pytest `
    --distpath $distRoot `
    --workpath $buildRoot `
    --specpath $specRoot `
    $entrypoint
if ($LASTEXITCODE -ne 0) { throw "Angmoo product sidecar packaging failed" }

$targetTriple = (& rustc --print host-tuple).Trim()
if (-not $targetTriple) { throw "Rust host target could not be determined" }
$source = Join-Path $distRoot "angmoo-sidecar.exe"
$target = Join-Path $binaryRoot "angmoo-sidecar-$targetTriple.exe"
$hashTarget = "$target.sha256"
Copy-Item -LiteralPath $source -Destination $target -Force
$stream = [System.IO.File]::OpenRead($target)
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
Set-Content -LiteralPath $hashTarget -Value $hash -Encoding ascii -NoNewline

[ordered]@{
    schema_version = 1
    status = "PASS"
    target = $targetTriple
    sidecar = $target
    sha256 = $hash
    bytes = (Get-Item -LiteralPath $target).Length
} | ConvertTo-Json
