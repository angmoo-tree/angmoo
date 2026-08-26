[CmdletBinding()]
param(
    [switch]$SkipHostBuild,
    [string]$HostPath,
    [string]$SidecarPath,
    [string]$ManifestPath,
    [string]$ProductVersion,
    [string]$BuildCommit
)

$ErrorActionPreference = 'Stop'
$desktopRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$repositoryRoot = (Resolve-Path (Join-Path $desktopRoot '..')).Path
$tauriRoot = Join-Path $desktopRoot 'src-tauri'
$releaseRoot = Join-Path $tauriRoot 'target\release'
if ([string]::IsNullOrWhiteSpace($HostPath)) {
    $HostPath = Join-Path $releaseRoot 'angmoo-desktop.exe'
}
if ([string]::IsNullOrWhiteSpace($SidecarPath)) {
    $SidecarPath = Join-Path $tauriRoot 'binaries\angmoo-sidecar-x86_64-pc-windows-msvc.exe'
}
if ([string]::IsNullOrWhiteSpace($ManifestPath)) {
    $ManifestPath = Join-Path $tauriRoot 'installer-payload.json'
}
$HostPath = [System.IO.Path]::GetFullPath($HostPath)
$SidecarPath = [System.IO.Path]::GetFullPath($SidecarPath)
$ManifestPath = [System.IO.Path]::GetFullPath($ManifestPath)

function Get-Sha256Hex([string]$Path) {
    $stream = [System.IO.File]::OpenRead($Path)
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $digest = $sha256.ComputeHash($stream)
        return [System.BitConverter]::ToString($digest).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $sha256.Dispose()
        $stream.Dispose()
    }
}

function Get-IntegerConstant([string]$Path, [string]$Name) {
    $content = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
    $pattern = '(?m)^' + [regex]::Escape($Name) + '\s*=\s*([0-9]+)\s*$'
    $match = [regex]::Match($content, $pattern)
    if (-not $match.Success) {
        throw "installer_payload_constant_missing:$Name"
    }
    return [int]$match.Groups[1].Value
}

function Get-MinimumManifestVersion([string]$Directory) {
    $versions = @(
        Get-ChildItem -LiteralPath $Directory -Filter 'v*.json' -File |
            ForEach-Object {
                if ($_.BaseName -match '^v([0-9]+)$') {
                    [int]$Matches[1]
                }
            }
    )
    if ($versions.Count -eq 0) {
        throw "installer_payload_version_manifest_missing:$Directory"
    }
    return [int](($versions | Measure-Object -Minimum).Minimum)
}

if (-not $IsWindows -and $PSVersionTable.PSEdition -eq 'Core') {
    throw 'installer_payload_requires_windows'
}

if (-not $SkipHostBuild) {
    Push-Location $repositoryRoot
    try {
        cargo build --manifest-path desktop\src-tauri\Cargo.toml --release --locked
        if ($LASTEXITCODE -ne 0) { throw 'installer_payload_host_build_failed' }
    }
    finally {
        Pop-Location
    }
}

foreach ($required in @($HostPath, $SidecarPath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "installer_payload_missing:$required"
    }
}

if ([string]::IsNullOrWhiteSpace($ProductVersion)) {
    $package = Get-Content -LiteralPath (Join-Path $desktopRoot 'package.json') -Raw -Encoding UTF8 |
        ConvertFrom-Json
    $ProductVersion = [string]$package.version
}
if ($ProductVersion -notmatch '^[0-9A-Za-z][0-9A-Za-z.+-]{0,63}$') {
    throw 'installer_payload_product_version_invalid'
}

if ([string]::IsNullOrWhiteSpace($BuildCommit)) {
    $BuildCommit = (& git -C $repositoryRoot rev-parse HEAD 2>$null).Trim()
}
if ($BuildCommit -notmatch '^[0-9a-f]{40}$') {
    throw 'installer_payload_build_commit_invalid'
}

$sqliteTarget = Get-IntegerConstant `
    (Join-Path $repositoryRoot 'backend\app\runtime\persistence\sqlite_schema.py') `
    'SQLITE_SCHEMA_VERSION'
$ladybugTarget = Get-IntegerConstant `
    (Join-Path $repositoryRoot 'backend\app\integrations\ladybug_projection.py') `
    'LADYBUG_PROJECTION_SCHEMA_VERSION'
$sqliteMinimum = Get-MinimumManifestVersion `
    (Join-Path $repositoryRoot 'backend\app\runtime\migrations\sqlite_versions\manifests')
# Keep the manifest inventory check even though pre-versioned Ladybug data is
# intentionally accepted below as a replayable source.
$null = Get-MinimumManifestVersion `
    (Join-Path $repositoryRoot 'backend\app\runtime\migrations\ladybug_versions\manifests')
# A pre-versioned Ladybug projection is rebuildable from SQLite canonical
# evidence. Version zero is therefore an intentionally readable source, not a
# second supported graph runtime.
$ladybugMinimum = 0

$hostSha256 = Get-Sha256Hex $HostPath
$sidecarSha256 = Get-Sha256Hex $SidecarPath
$identitySource = @(
    $ProductVersion,
    $BuildCommit,
    $hostSha256,
    $sidecarSha256,
    "sqlite:$sqliteMinimum-$sqliteTarget->$sqliteTarget",
    "ladybug:$ladybugMinimum-$ladybugTarget->$ladybugTarget"
) -join "`n"
$identityBytes = [System.Text.Encoding]::UTF8.GetBytes($identitySource)
$identityHasher = [System.Security.Cryptography.SHA256]::Create()
try {
    $payloadGeneration = [System.BitConverter]::ToString(
        $identityHasher.ComputeHash($identityBytes)
    ).Replace('-', '').ToLowerInvariant()
}
finally {
    $identityHasher.Dispose()
}

$payload = [ordered]@{
    schema_version = 2
    product_version = $ProductVersion
    build_commit = $BuildCommit
    payload_generation = $payloadGeneration
    embedded_data = [ordered]@{
        sqlite = [ordered]@{
            minimum_readable_version = $sqliteMinimum
            maximum_readable_version = $sqliteTarget
            target_version = $sqliteTarget
        }
        ladybug = [ordered]@{
            minimum_readable_version = $ladybugMinimum
            maximum_readable_version = $ladybugTarget
            target_version = $ladybugTarget
        }
    }
    files = [ordered]@{
        'angmoo-desktop.exe' = $hostSha256
        'angmoo-sidecar.exe' = $sidecarSha256
    }
}
$json = $payload | ConvertTo-Json -Depth 4 -Compress
[System.IO.File]::WriteAllText($ManifestPath, $json + "`n", [System.Text.UTF8Encoding]::new($false))
Write-Output "installer_payload_manifest_ready:$ManifestPath"
