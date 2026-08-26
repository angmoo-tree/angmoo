[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$AppRoot,
    [ValidateRange(1, 40)]
    [int]$HashAttempts = 8,
    [ValidateRange(10, 5000)]
    [int]$HashRetryMilliseconds = 125
)

$ErrorActionPreference = 'Stop'
function Get-Sha256HexOnce([string]$Path) {
    $stream = [System.IO.File]::Open(
        $Path,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete
    )
    try {
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        try {
            $digest = $sha256.ComputeHash($stream)
            return [System.BitConverter]::ToString($digest).Replace('-', '').ToLowerInvariant()
        }
        finally {
            $sha256.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
}

function Get-StableSha256Hex([string]$Path) {
    for ($attempt = 1; $attempt -le $HashAttempts; $attempt++) {
        try {
            $first = Get-Sha256HexOnce $Path
            Start-Sleep -Milliseconds 25
            $second = Get-Sha256HexOnce $Path
            if ([string]::Equals($first, $second, [System.StringComparison]::Ordinal)) {
                return $first
            }
        }
        catch [System.IO.IOException] {
            # Defender and the Windows installer service can hold a bounded
            # transient read lock. Retry, but never accept an unreadable file.
        }
        catch [System.UnauthorizedAccessException] {
            # Treat a transient scanner ACL/open race exactly like a read lock.
        }
        if ($attempt -lt $HashAttempts) {
            Start-Sleep -Milliseconds $HashRetryMilliseconds
        }
    }
    return $null
}

function Get-IdentitySha256([object]$Manifest) {
    $identitySource = @(
        [string]$Manifest.product_version,
        [string]$Manifest.build_commit,
        [string]$Manifest.files.'angmoo-desktop.exe',
        [string]$Manifest.files.'angmoo-sidecar.exe',
        "sqlite:$($Manifest.embedded_data.sqlite.minimum_readable_version)-$($Manifest.embedded_data.sqlite.maximum_readable_version)->$($Manifest.embedded_data.sqlite.target_version)",
        "ladybug:$($Manifest.embedded_data.ladybug.minimum_readable_version)-$($Manifest.embedded_data.ladybug.maximum_readable_version)->$($Manifest.embedded_data.ladybug.target_version)"
    ) -join "`n"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($identitySource)
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        return [System.BitConverter]::ToString(
            $hasher.ComputeHash($bytes)
        ).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $hasher.Dispose()
    }
}

$root = [System.IO.Path]::GetFullPath($AppRoot).TrimEnd('\')
$productRoot = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Angmoo')).TrimEnd('\')
$allowedRoots = @(
    [System.IO.Path]::GetFullPath((Join-Path $productRoot 'app')).TrimEnd('\'),
    [System.IO.Path]::GetFullPath((Join-Path $productRoot 'app.__install_staging__')).TrimEnd('\'),
    [System.IO.Path]::GetFullPath((Join-Path $productRoot 'app.__install_backup__')).TrimEnd('\')
)
$matchingRoots = @(
    $allowedRoots | Where-Object {
        [string]::Equals($root, $_, [System.StringComparison]::OrdinalIgnoreCase)
    }
)
if ($matchingRoots.Count -ne 1) {
    [Console]::Error.WriteLine('installer_payload_root_invalid')
    exit 31
}

$manifestPath = Join-Path $root 'installer-payload.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    [Console]::Error.WriteLine('installer_payload_manifest_missing')
    exit 32
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.schema_version -notin @(1, 2)) {
    [Console]::Error.WriteLine('installer_payload_manifest_invalid')
    exit 33
}

if ($manifest.schema_version -eq 2) {
    $sqlite = $manifest.embedded_data.sqlite
    $ladybug = $manifest.embedded_data.ladybug
    $identityValid = (
        [string]$manifest.product_version -match '^[0-9A-Za-z][0-9A-Za-z.+-]{0,63}$' -and
        [string]$manifest.build_commit -match '^[0-9a-f]{40}$' -and
        [string]$manifest.payload_generation -match '^[0-9a-f]{64}$' -and
        [int]$sqlite.minimum_readable_version -ge 1 -and
        [int]$sqlite.minimum_readable_version -le [int]$sqlite.maximum_readable_version -and
        [int]$sqlite.target_version -ge [int]$sqlite.minimum_readable_version -and
        [int]$sqlite.maximum_readable_version -ge [int]$sqlite.target_version -and
        [int]$ladybug.minimum_readable_version -ge 0 -and
        [int]$ladybug.minimum_readable_version -le [int]$ladybug.maximum_readable_version -and
        [int]$ladybug.target_version -ge [int]$ladybug.minimum_readable_version -and
        [int]$ladybug.maximum_readable_version -ge [int]$ladybug.target_version
    )
    if (-not $identityValid -or
        -not [string]::Equals(
            (Get-IdentitySha256 $manifest),
            [string]$manifest.payload_generation,
            [System.StringComparison]::Ordinal
        )) {
        [Console]::Error.WriteLine('installer_payload_manifest_invalid')
        exit 33
    }
}

foreach ($name in @('angmoo-desktop.exe', 'angmoo-sidecar.exe')) {
    $path = Join-Path $root $name
    $expected = $manifest.files.$name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or $expected -notmatch '^[0-9a-f]{64}$') {
        [Console]::Error.WriteLine("installer_payload_entry_invalid:$name")
        exit 34
    }
    $actual = Get-StableSha256Hex $path
    if ($null -eq $actual) {
        [Console]::Error.WriteLine("installer_payload_hash_timeout:$name")
        exit 37
    }
    if (-not [string]::Equals($actual, $expected, [System.StringComparison]::Ordinal)) {
        [Console]::Error.WriteLine("installer_payload_digest_mismatch:$name")
        exit 35
    }
}

$unexpectedExecutables = @(
    Get-ChildItem -LiteralPath $root -File -Filter '*.exe' |
        Where-Object { $_.Name -notin @(
            'angmoo-desktop.exe',
            'angmoo-sidecar.exe',
            'uninstall.exe'
        ) }
)
if ($unexpectedExecutables.Count -gt 0) {
    [Console]::Error.WriteLine('installer_payload_unexpected_executable')
    exit 36
}

Write-Output 'installer_payload_digest_parity_pass'
exit 0
