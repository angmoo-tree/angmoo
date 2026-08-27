[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$probeRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    'angmoo-payload-probe-' + [guid]::NewGuid().ToString('N')
)
$fakeLocalAppData = Join-Path $probeRoot 'local'
$appRoot = Join-Path $fakeLocalAppData 'Angmoo\app'
$verifier = Join-Path $PSScriptRoot 'verify-installed-payload.ps1'
$originalLocalAppData = $env:LOCALAPPDATA
$currentPowerShell = (Get-Process -Id $PID).Path

try {
    New-Item -ItemType Directory -Force -Path $appRoot | Out-Null
    [System.IO.File]::WriteAllBytes(
        (Join-Path $appRoot 'angmoo-desktop.exe'),
        [byte[]](0x4d, 0x5a, 0x01)
    )
    [System.IO.File]::WriteAllBytes(
        (Join-Path $appRoot 'angmoo-sidecar.exe'),
        [byte[]](0x4d, 0x5a, 0x02)
    )
    $payload = [ordered]@{
        schema_version = 2
        product_version = '0.4.0-1'
        build_commit = ('a' * 40 -join '')
        embedded_data = [ordered]@{
            sqlite = [ordered]@{
                minimum_readable_version = 1
                maximum_readable_version = 2
                target_version = 2
            }
            ladybug = [ordered]@{
                minimum_readable_version = 0
                maximum_readable_version = 1
                target_version = 1
            }
        }
        files = [ordered]@{
            'angmoo-desktop.exe' = (
                Get-FileHash -LiteralPath (Join-Path $appRoot 'angmoo-desktop.exe') -Algorithm SHA256
            ).Hash.ToLowerInvariant()
            'angmoo-sidecar.exe' = (
                Get-FileHash -LiteralPath (Join-Path $appRoot 'angmoo-sidecar.exe') -Algorithm SHA256
            ).Hash.ToLowerInvariant()
        }
    }
    $identitySource = @(
        $payload.product_version,
        $payload.build_commit,
        $payload.files.'angmoo-desktop.exe',
        $payload.files.'angmoo-sidecar.exe',
        'sqlite:1-2->2',
        'ladybug:0-1->1'
    ) -join "`n"
    $identityHasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $payload.payload_generation = [System.BitConverter]::ToString(
            $identityHasher.ComputeHash(
                [System.Text.Encoding]::UTF8.GetBytes($identitySource)
            )
        ).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $identityHasher.Dispose()
    }
    [System.IO.File]::WriteAllText(
        (Join-Path $appRoot 'installer-payload.json'),
        (($payload | ConvertTo-Json -Depth 4 -Compress) + "`n"),
        [System.Text.UTF8Encoding]::new($false)
    )

    $env:LOCALAPPDATA = $fakeLocalAppData
    & $currentPowerShell -NoProfile -NonInteractive -File $verifier -AppRoot $appRoot
    if ($LASTEXITCODE -ne 0) {
        throw 'installer_payload_verifier_positive_probe_failed'
    }

    [System.IO.File]::WriteAllBytes(
        (Join-Path $appRoot 'angmoo-sidecar.exe'),
        [byte[]](0x4d, 0x5a, 0x03)
    )
    # PowerShell 7.6 promotes a child pwsh stderr record to a terminating
    # NativeCommandError when this script uses Stop. The non-zero exit is the
    # expected negative probe, so capture it before restoring strict handling.
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $currentPowerShell -NoProfile -NonInteractive -File $verifier -AppRoot $appRoot 2>$null
        $negativeExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($negativeExitCode -ne 35) {
        throw "installer_payload_verifier_negative_probe_failed:$negativeExitCode"
    }
    Write-Output 'installer_payload_verifier_positive_and_negative_pass'
}
finally {
    $env:LOCALAPPDATA = $originalLocalAppData
    if (Test-Path -LiteralPath $probeRoot) {
        Remove-Item -LiteralPath $probeRoot -Recurse -Force
    }
}

exit 0
