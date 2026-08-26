[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$probeRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    'angmoo-payload-transaction-' + [guid]::NewGuid().ToString('N')
)
$fakeLocalAppData = Join-Path $probeRoot 'local'
$productRoot = Join-Path $fakeLocalAppData 'Angmoo'
$app = Join-Path $productRoot 'app'
$staging = Join-Path $productRoot 'app.__install_staging__'
$backup = Join-Path $productRoot 'app.__install_backup__'
$verifier = Join-Path $PSScriptRoot 'verify-installed-payload.ps1'
$transaction = Join-Path $PSScriptRoot 'installer-payload-transaction.ps1'
$shell = (Get-Process -Id $PID).Path
$originalLocalAppData = $env:LOCALAPPDATA

function Get-HexSha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Write-Payload([string]$Root, [byte]$Generation, [int]$SchemaVersion = 2) {
    New-Item -ItemType Directory -Force -Path $Root | Out-Null
    [System.IO.File]::WriteAllBytes(
        (Join-Path $Root 'angmoo-desktop.exe'),
        [byte[]](0x4d, 0x5a, $Generation, 0x01)
    )
    [System.IO.File]::WriteAllBytes(
        (Join-Path $Root 'angmoo-sidecar.exe'),
        [byte[]](0x4d, 0x5a, $Generation, 0x02)
    )
    $hostDigest = Get-HexSha256 (Join-Path $Root 'angmoo-desktop.exe')
    $sidecarDigest = Get-HexSha256 (Join-Path $Root 'angmoo-sidecar.exe')
    if ($SchemaVersion -eq 1) {
        $payload = [ordered]@{
            schema_version = 1
            files = [ordered]@{
                'angmoo-desktop.exe' = $hostDigest
                'angmoo-sidecar.exe' = $sidecarDigest
            }
        }
    }
    else {
        $build = (([char](96 + [int]$Generation)).ToString() * 40 -join '')
        $identity = @(
            '0.4.0-1',
            $build,
            $hostDigest,
            $sidecarDigest,
            'sqlite:1-2->2',
            'ladybug:0-1->1'
        ) -join "`n"
        $hasher = [System.Security.Cryptography.SHA256]::Create()
        try {
            $generationHash = [System.BitConverter]::ToString(
                $hasher.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($identity))
            ).Replace('-', '').ToLowerInvariant()
        }
        finally {
            $hasher.Dispose()
        }
        $payload = [ordered]@{
            schema_version = 2
            product_version = '0.4.0-1'
            build_commit = $build
            payload_generation = $generationHash
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
                'angmoo-desktop.exe' = $hostDigest
                'angmoo-sidecar.exe' = $sidecarDigest
            }
        }
    }
    [System.IO.File]::WriteAllText(
        (Join-Path $Root 'installer-payload.json'),
        (($payload | ConvertTo-Json -Depth 5 -Compress) + "`n"),
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Invoke-Transaction([string]$Action, [int]$ExpectedExit = 0) {
    $previous = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $shell -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass `
            -File $transaction -Action $Action -ProductRoot $productRoot `
            -VerifierPath $verifier *> $null
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previous
    }
    if ($exitCode -ne $ExpectedExit) {
        throw "installer_payload_transaction_probe_failed:$Action`:$exitCode"
    }
}

try {
    $env:LOCALAPPDATA = $fakeLocalAppData

    # A verified previous schema-1 payload stays live until schema-2 staging is
    # complete, then becomes the rollback candidate.
    Write-Payload $app 1 1
    $oldHostHash = Get-HexSha256 (Join-Path $app 'angmoo-desktop.exe')
    Invoke-Transaction Prepare
    if ((Get-HexSha256 (Join-Path $app 'angmoo-desktop.exe')) -ne $oldHostHash) {
        throw 'installer_prepare_changed_current_app'
    }
    Write-Payload $staging 2
    Invoke-Transaction Promote
    if (-not (Test-Path -LiteralPath $backup)) {
        throw 'installer_promotion_backup_missing'
    }
    if ((Get-HexSha256 (Join-Path $backup 'angmoo-desktop.exe')) -ne $oldHostHash) {
        throw 'installer_promotion_backup_changed'
    }
    Invoke-Transaction Finalize
    if ((Test-Path -LiteralPath $backup) -or (Test-Path -LiteralPath $staging)) {
        throw 'installer_finalize_left_transaction_root'
    }

    # A mixed existing app is never trusted as rollback material, but a fully
    # verified staging payload repairs it safely.
    [System.IO.File]::WriteAllBytes(
        (Join-Path $app 'angmoo-sidecar.exe'),
        [byte[]](0x4d, 0x5a, 0xff)
    )
    Invoke-Transaction Prepare
    Write-Payload $staging 3
    Invoke-Transaction Promote
    if (Test-Path -LiteralPath $backup) {
        throw 'installer_mixed_payload_was_trusted_as_backup'
    }
    Invoke-Transaction Finalize

    # An interrupted promotion with only a verified backup is recovered before
    # a new staging directory is created.
    [System.IO.Directory]::Move($app, $backup)
    Invoke-Transaction Prepare
    if (-not (Test-Path -LiteralPath $app)) {
        throw 'installer_verified_backup_not_recovered'
    }
    Remove-Item -LiteralPath $staging -Recurse -Force

    # Tampered staging cannot replace the current verified app.
    $currentHash = Get-HexSha256 (Join-Path $app 'angmoo-desktop.exe')
    Invoke-Transaction Prepare
    Write-Payload $staging 4
    [System.IO.File]::WriteAllBytes(
        (Join-Path $staging 'angmoo-sidecar.exe'),
        [byte[]](0x4d, 0x5a, 0xee)
    )
    Invoke-Transaction Promote 50
    if ((Get-HexSha256 (Join-Path $app 'angmoo-desktop.exe')) -ne $currentHash) {
        throw 'installer_tampered_staging_changed_current_app'
    }

    Write-Output 'installer_payload_transaction_matrix_pass'
}
finally {
    $env:LOCALAPPDATA = $originalLocalAppData
    if (Test-Path -LiteralPath $probeRoot) {
        Remove-Item -LiteralPath $probeRoot -Recurse -Force
    }
}

exit 0
