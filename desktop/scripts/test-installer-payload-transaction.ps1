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
$script:transactionProbe = 0

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
            'ladybug:0-2->2'
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
                    maximum_readable_version = 2
                    target_version = 2
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

function Write-DataMarker([string]$Kind, [int]$Version) {
    $root = Join-Path $productRoot $Kind
    New-Item -ItemType Directory -Force -Path $root | Out-Null
    $payload = [ordered]@{
        schema_version = 1
        generation = 'fixture'
        relative_path = 'generations/fixture'
        content_sha256 = ('d' * 64)
        manifest_sha256 = ('e' * 64)
        data_version = $Version
    }
    [System.IO.File]::WriteAllText(
        (Join-Path $root 'current-generation.json'),
        (($payload | ConvertTo-Json -Depth 4 -Compress) + "`n"),
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Invoke-Transaction(
    [string]$Action,
    [int]$ExpectedExit = 0,
    [string]$FailureCode = '',
    [string]$ResultPath = ''
) {
    $script:transactionProbe += 1
    $previous = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        if ($FailureCode -and $ResultPath) {
            $probeOutput = & $shell -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass `
                -File $transaction -Action $Action -ProductRoot $productRoot `
                -VerifierPath $verifier -FailureCode $FailureCode `
                -ResultPath $ResultPath 2>&1
        }
        elseif ($FailureCode) {
            $probeOutput = & $shell -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass `
                -File $transaction -Action $Action -ProductRoot $productRoot `
                -VerifierPath $verifier -FailureCode $FailureCode 2>&1
        }
        else {
            $probeOutput = & $shell -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass `
                -File $transaction -Action $Action -ProductRoot $productRoot `
                -VerifierPath $verifier 2>&1
        }
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previous
    }
    if ($exitCode -ne $ExpectedExit) {
        $detail = @($probeOutput) -join '|'
        throw "installer_payload_transaction_probe_failed:$($script:transactionProbe):$Action`:$exitCode`:$detail"
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

    # A post-promotion data migration failure restores the exact verified
    # predecessor instead of leaving a new app paired with unreadable data.
    $restorableHash = Get-HexSha256 (Join-Path $app 'angmoo-desktop.exe')
    Invoke-Transaction Prepare
    Write-Payload $staging 5
    Invoke-Transaction Promote
    Write-DataMarker canonical 2
    Write-DataMarker graph 1
    $installerResult = Join-Path $productRoot 'runtime\installer-data-upgrade-result.json'
    $promotedManifest = Get-Content -LiteralPath (
        Join-Path $app 'installer-payload.json'
    ) -Raw -Encoding UTF8 | ConvertFrom-Json
    $failureResult = [ordered]@{
        schema_version = 1
        status = 'failed'
        operation = 'upgrade'
        code = 'sqlite_migration_reserved_role_conflict'
        build_commit = [string]$promotedManifest.build_commit
        payload_generation = [string]$promotedManifest.payload_generation
        sqlite_source_version = 2
        sqlite_target_version = 3
        sqlite_active_version = 2
        ladybug_source_version = 1
        ladybug_target_version = 2
        ladybug_active_version = 1
    }
    [System.IO.File]::WriteAllText(
        $installerResult,
        (($failureResult | ConvertTo-Json -Depth 4 -Compress) + "`n"),
        [System.Text.UTF8Encoding]::new($false)
    )
    Invoke-Transaction `
        RestoreFailure `
        0 `
        'installer_embedded_data_migration_failed' `
        $installerResult
    if ((Get-HexSha256 (Join-Path $app 'angmoo-desktop.exe')) -ne $restorableHash) {
        throw 'installer_data_failure_did_not_restore_previous_app'
    }
    if ((Test-Path -LiteralPath $backup) -or (Test-Path -LiteralPath $staging)) {
        throw 'installer_data_failure_left_transaction_root'
    }
    $restoredState = Get-Content -LiteralPath (
        Join-Path $productRoot 'runtime\installer-transaction.json'
    ) -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([string]$restoredState.phase -ne 'failed_restored') {
        throw 'installer_data_failure_state_not_restored'
    }
    if ([string]$restoredState.existing_payload -ne 'sqlite_migration_reserved_role_conflict') {
        throw 'installer_data_failure_detail_not_preserved'
    }

    # A concrete source/active version in the sidecar result requires the
    # corresponding active marker to still exist. Missing marker evidence is
    # fail-closed: retain the promoted payload and refuse an unsafe rollback.
    Invoke-Transaction Prepare
    Write-Payload $staging 4
    Invoke-Transaction Promote
    $markerMissingHash = Get-HexSha256 (Join-Path $app 'angmoo-desktop.exe')
    $promotedManifest = Get-Content -LiteralPath (
        Join-Path $app 'installer-payload.json'
    ) -Raw -Encoding UTF8 | ConvertFrom-Json
    $failureResult.build_commit = [string]$promotedManifest.build_commit
    $failureResult.payload_generation = [string]$promotedManifest.payload_generation
    $failureResult.sqlite_active_version = 2
    Remove-Item -LiteralPath (
        Join-Path $productRoot 'canonical\current-generation.json'
    ) -Force
    [System.IO.File]::WriteAllText(
        $installerResult,
        (($failureResult | ConvertTo-Json -Depth 4 -Compress) + "`n"),
        [System.Text.UTF8Encoding]::new($false)
    )
    Invoke-Transaction `
        RestoreFailure `
        50 `
        'installer_embedded_data_migration_failed' `
        $installerResult
    if ((Get-HexSha256 (Join-Path $app 'angmoo-desktop.exe')) -ne $markerMissingHash) {
        throw 'installer_missing_marker_restored_previous_app'
    }
    if (-not (Test-Path -LiteralPath $backup -PathType Container)) {
        throw 'installer_missing_marker_removed_rollback_evidence'
    }

    # Once the active data marker has advanced beyond the recorded source, an
    # old app is no longer a safe rollback target and must not replace the new
    # verified payload.
    Invoke-Transaction Prepare
    Write-Payload $staging 4
    Invoke-Transaction Promote
    $advancedHash = Get-HexSha256 (Join-Path $app 'angmoo-desktop.exe')
    Write-DataMarker canonical 3
    $promotedManifest = Get-Content -LiteralPath (
        Join-Path $app 'installer-payload.json'
    ) -Raw -Encoding UTF8 | ConvertFrom-Json
    $failureResult.build_commit = [string]$promotedManifest.build_commit
    $failureResult.payload_generation = [string]$promotedManifest.payload_generation
    $failureResult.sqlite_active_version = 3
    [System.IO.File]::WriteAllText(
        $installerResult,
        (($failureResult | ConvertTo-Json -Depth 4 -Compress) + "`n"),
        [System.Text.UTF8Encoding]::new($false)
    )
    Invoke-Transaction `
        RestoreFailure `
        50 `
        'installer_embedded_data_migration_failed' `
        $installerResult
    if ((Get-HexSha256 (Join-Path $app 'angmoo-desktop.exe')) -ne $advancedHash) {
        throw 'installer_advanced_data_restored_incompatible_app'
    }
    Remove-Item -LiteralPath $backup -Recurse -Force

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

    # A corrupt rollback candidate is rejected before the promoted app is
    # touched. The installer must fail closed rather than trusting the backup.
    Remove-Item -LiteralPath $staging -Recurse -Force
    Invoke-Transaction Prepare
    Write-Payload $staging 6
    Invoke-Transaction Promote
    $promotedHash = Get-HexSha256 (Join-Path $app 'angmoo-desktop.exe')
    [System.IO.File]::WriteAllBytes(
        (Join-Path $backup 'angmoo-sidecar.exe'),
        [byte[]](0x4d, 0x5a, 0xdd)
    )
    Invoke-Transaction `
        RestoreFailure `
        50 `
        'installer_embedded_data_migration_failed'
    if ((Get-HexSha256 (Join-Path $app 'angmoo-desktop.exe')) -ne $promotedHash) {
        throw 'installer_invalid_backup_changed_promoted_app'
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
