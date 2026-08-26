[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$AppRoot
)

$ErrorActionPreference = 'Stop'
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

$root = [System.IO.Path]::GetFullPath($AppRoot).TrimEnd('\')
$expectedRoot = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Angmoo\app')).TrimEnd('\')
if (-not [string]::Equals($root, $expectedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    [Console]::Error.WriteLine('installer_payload_root_invalid')
    exit 31
}

$manifestPath = Join-Path $root 'installer-payload.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    [Console]::Error.WriteLine('installer_payload_manifest_missing')
    exit 32
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.schema_version -ne 1) {
    [Console]::Error.WriteLine('installer_payload_manifest_invalid')
    exit 33
}

foreach ($name in @('angmoo-desktop.exe', 'angmoo-sidecar.exe')) {
    $path = Join-Path $root $name
    $expected = $manifest.files.$name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or $expected -notmatch '^[0-9a-f]{64}$') {
        [Console]::Error.WriteLine("installer_payload_entry_invalid:$name")
        exit 34
    }
    $actual = Get-Sha256Hex $path
    if (-not [string]::Equals($actual, $expected, [System.StringComparison]::Ordinal)) {
        [Console]::Error.WriteLine("installer_payload_digest_mismatch:$name")
        exit 35
    }
}

Write-Output 'installer_payload_digest_parity_pass'
exit 0
