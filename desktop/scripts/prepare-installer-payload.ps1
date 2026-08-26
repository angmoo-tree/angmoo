[CmdletBinding()]
param(
    [switch]$SkipHostBuild,
    [string]$HostPath,
    [string]$SidecarPath,
    [string]$ManifestPath
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

$payload = [ordered]@{
    schema_version = 1
    files = [ordered]@{
        'angmoo-desktop.exe' = Get-Sha256Hex $HostPath
        'angmoo-sidecar.exe' = Get-Sha256Hex $SidecarPath
    }
}
$json = $payload | ConvertTo-Json -Depth 4 -Compress
[System.IO.File]::WriteAllText($ManifestPath, $json + "`n", [System.Text.UTF8Encoding]::new($false))
Write-Output "installer_payload_manifest_ready:$ManifestPath"
