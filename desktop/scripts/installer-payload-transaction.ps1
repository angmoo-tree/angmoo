[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Prepare', 'Promote', 'Finalize', 'RestoreFailure', 'RecordFailure')]
    [string]$Action,
    [Parameter(Mandatory = $true)]
    [string]$ProductRoot,
    [Parameter(Mandatory = $true)]
    [string]$VerifierPath,
    [string]$FailureCode,
    [string]$ResultPath
)

$ErrorActionPreference = 'Stop'
$stableFailure = 'installer_payload_transaction_failed'

function Assert-ExactProductRoot([string]$Path) {
    $actual = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
    $expected = [System.IO.Path]::GetFullPath(
        (Join-Path $env:LOCALAPPDATA 'Angmoo')
    ).TrimEnd('\')
    if (-not [string]::Equals(
        $actual,
        $expected,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw 'installer_product_root_invalid'
    }
    return $actual
}

function Assert-NoReparsePoint([string]$Path, [switch]$Recursive) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    $item = Get-Item -LiteralPath $Path -Force
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'installer_payload_reparse_refused'
    }
    if ($Recursive -and $item.PSIsContainer) {
        $reparse = Get-ChildItem -LiteralPath $Path -Force -Recurse |
            Where-Object {
                ($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
            } |
            Select-Object -First 1
        if ($null -ne $reparse) {
            throw 'installer_payload_reparse_refused'
        }
    }
}

function Remove-OwnedDirectory([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    Assert-NoReparsePoint $Path -Recursive
    Remove-Item -LiteralPath $Path -Recurse -Force
}

function Test-VerifiedPayload([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        return $false
    }
    Assert-NoReparsePoint $Path -Recursive
    $shell = (Get-Process -Id $PID).Path
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $shell -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass `
            -File $VerifierPath -AppRoot $Path *> $null
        return $LASTEXITCODE -eq 0
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Get-CandidateIdentity([string]$Path) {
    $manifestPath = Join-Path $Path 'installer-payload.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        return [ordered]@{
            product_version = 'unknown'
            build_commit = 'unknown'
            payload_generation = 'unknown'
        }
    }
    try {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 |
            ConvertFrom-Json
        return [ordered]@{
            product_version = [string]$manifest.product_version
            build_commit = [string]$manifest.build_commit
            payload_generation = [string]$manifest.payload_generation
        }
    }
    catch {
        return [ordered]@{
            product_version = 'invalid'
            build_commit = 'invalid'
            payload_generation = 'invalid'
        }
    }
}

function Read-InstallerFailureResult([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw 'installer_result_missing'
    }
    $actual = [System.IO.Path]::GetFullPath($Path)
    $expected = [System.IO.Path]::GetFullPath(
        (Join-Path $script:productRoot 'runtime\installer-data-upgrade-result.json')
    )
    if (-not [string]::Equals(
        $actual,
        $expected,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw 'installer_result_path_invalid'
    }
    if (-not (Test-Path -LiteralPath $actual -PathType Leaf)) {
        throw 'installer_result_missing'
    }
    try {
        $result = Get-Content -LiteralPath $actual -Raw -Encoding UTF8 |
            ConvertFrom-Json
        $candidate = [string]$result.code
        $required = @(
            'sqlite_source_version',
            'sqlite_target_version',
            'sqlite_active_version',
            'ladybug_source_version',
            'ladybug_target_version',
            'ladybug_active_version',
            'build_commit',
            'payload_generation'
        )
        $valid = (
            [int]$result.schema_version -eq 1 -and
            [string]$result.status -eq 'failed' -and
            [string]$result.operation -eq 'upgrade' -and
            $candidate -match '^(installer|sqlite|ladybug)_[a-z0-9_]+$' -and
            @($required | Where-Object {
                $_ -notin $result.PSObject.Properties.Name
            }).Count -eq 0
        )
        if ($valid) {
            return $result
        }
    }
    catch {
        # A malformed result is never trusted as app/data rollback authority.
    }
    throw 'installer_result_invalid'
}

function Read-ActiveDataVersion([string]$Kind) {
    $markerPath = Join-Path $script:productRoot "$Kind\current-generation.json"
    if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
        return $null
    }
    try {
        $marker = Get-Content -LiteralPath $markerPath -Raw -Encoding UTF8 |
            ConvertFrom-Json
        if (
            [int]$marker.schema_version -ne 1 -or
            [int]$marker.data_version -lt 0
        ) {
            throw 'invalid'
        }
        return [int]$marker.data_version
    }
    catch {
        throw 'installer_active_data_marker_invalid'
    }
}

function Assert-RollbackDataCompatibility(
    [object]$Result,
    [string]$BackupRoot,
    [string]$ActiveAppRoot
) {
    $activeIdentity = Get-CandidateIdentity $ActiveAppRoot
    if (
        [string]$Result.build_commit -ne $activeIdentity.build_commit -or
        [string]$Result.payload_generation -ne $activeIdentity.payload_generation
    ) {
        throw 'installer_result_payload_mismatch'
    }

    $backupManifestPath = Join-Path $BackupRoot 'installer-payload.json'
    try {
        $backupManifest = Get-Content -LiteralPath $backupManifestPath `
            -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        throw 'installer_previous_payload_data_contract_invalid'
    }
    if ([int]$backupManifest.schema_version -ne 2) {
        throw 'installer_previous_payload_data_contract_invalid'
    }

    foreach ($contract in @(
        [ordered]@{
            kind = 'canonical'
            manifest = $backupManifest.embedded_data.sqlite
            source = $Result.sqlite_source_version
            active = $Result.sqlite_active_version
            target = $Result.sqlite_target_version
        },
        [ordered]@{
            kind = 'graph'
            manifest = $backupManifest.embedded_data.ladybug
            source = $Result.ladybug_source_version
            active = $Result.ladybug_active_version
            target = $Result.ladybug_target_version
        }
    )) {
        $sourceMissing = $null -eq $contract.source
        $activeMissing = $null -eq $contract.active
        if ($sourceMissing -ne $activeMissing) {
            throw 'installer_active_data_generation_changed'
        }
        if (-not $sourceMissing) {
            $source = [int]$contract.source
            $active = [int]$contract.active
            $target = [int]$contract.target
            if ($source -lt 0 -or $target -lt 0 -or $active -ne $source) {
                throw 'installer_active_data_generation_changed'
            }
            if (
                $source -lt [int]$contract.manifest.minimum_readable_version -or
                $source -gt [int]$contract.manifest.maximum_readable_version
            ) {
                throw 'installer_previous_payload_data_incompatible'
            }
        }

        $markerVersion = Read-ActiveDataVersion ([string]$contract.kind)
        if ($activeMissing) {
            if ($null -ne $markerVersion) {
                throw 'installer_active_data_generation_changed'
            }
        }
        elseif (
            $null -eq $markerVersion -or
            [int]$markerVersion -ne [int]$contract.active
        ) {
            # A failure result cannot authorize rollback when the active marker
            # disappeared after the sidecar recorded a concrete generation.
            # Treat marker loss exactly like an unexpected generation change.
            throw 'installer_active_data_generation_changed'
        }
    }
}

function Write-Diagnostic(
    [string]$Code,
    [string]$Phase,
    [string]$PayloadRoot
) {
    $identity = Get-CandidateIdentity $PayloadRoot
    $record = [ordered]@{
        schema_version = 1
        recorded_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
        phase = $Phase
        code = $Code
        product_version = $identity.product_version
        build_commit = $identity.build_commit
        payload_generation = $identity.payload_generation
    }
    $logs = Join-Path $script:productRoot 'logs'
    Assert-NoReparsePoint $logs
    New-Item -ItemType Directory -Force -Path $logs | Out-Null
    $line = $record | ConvertTo-Json -Depth 4 -Compress
    Add-Content -LiteralPath (Join-Path $logs 'installer-update.jsonl') `
        -Value $line -Encoding UTF8
}

function Write-State([string]$Phase, [string]$ExistingPayload) {
    $runtime = Join-Path $script:productRoot 'runtime'
    Assert-NoReparsePoint $runtime
    New-Item -ItemType Directory -Force -Path $runtime | Out-Null
    $statePath = Join-Path $runtime 'installer-transaction.json'
    $temporary = "$statePath.tmp"
    $identity = Get-CandidateIdentity $script:candidateRoot
    $state = [ordered]@{
        schema_version = 1
        phase = $Phase
        existing_payload = $ExistingPayload
        product_version = $identity.product_version
        build_commit = $identity.build_commit
        payload_generation = $identity.payload_generation
        updated_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
    }
    [System.IO.File]::WriteAllText(
        $temporary,
        (($state | ConvertTo-Json -Depth 4 -Compress) + "`n"),
        [System.Text.UTF8Encoding]::new($false)
    )
    Move-Item -LiteralPath $temporary -Destination $statePath -Force
}

try {
    $script:productRoot = Assert-ExactProductRoot $ProductRoot
    if (-not (Test-Path -LiteralPath $VerifierPath -PathType Leaf)) {
        throw 'installer_payload_verifier_missing'
    }
    Assert-NoReparsePoint $script:productRoot
    New-Item -ItemType Directory -Force -Path $script:productRoot | Out-Null

    $app = Join-Path $script:productRoot 'app'
    $staging = Join-Path $script:productRoot 'app.__install_staging__'
    $backup = Join-Path $script:productRoot 'app.__install_backup__'
    $script:candidateRoot = $staging

    switch ($Action) {
        'Prepare' {
            $existingState = if (Test-Path -LiteralPath $app) {
                if (Test-VerifiedPayload $app) { 'verified' } else { 'mixed' }
            } else {
                'absent'
            }

            if (Test-Path -LiteralPath $backup) {
                $appValid = Test-VerifiedPayload $app
                $backupValid = Test-VerifiedPayload $backup
                if ($appValid) {
                    Remove-OwnedDirectory $backup
                }
                elseif ($backupValid) {
                    Remove-OwnedDirectory $app
                    [System.IO.Directory]::Move($backup, $app)
                    $existingState = 'recovered_backup'
                }
                else {
                    throw 'installer_payload_recovery_unavailable'
                }
            }

            Remove-OwnedDirectory $staging
            New-Item -ItemType Directory -Force -Path $staging | Out-Null
            Write-State 'prepared' $existingState
            Write-Diagnostic 'installer_payload_staging_prepared' 'prepare' $staging
            Write-Output "installer_payload_transaction_prepared:$existingState"
        }
        'Promote' {
            if (-not (Test-VerifiedPayload $staging)) {
                throw 'installer_staging_digest_mismatch'
            }
            if (Test-Path -LiteralPath $backup) {
                throw 'installer_payload_backup_conflict'
            }
            $existingState = 'absent'
            if (Test-Path -LiteralPath $app) {
                if (Test-VerifiedPayload $app) {
                    [System.IO.Directory]::Move($app, $backup)
                    $existingState = 'verified_backup'
                }
                else {
                    Remove-OwnedDirectory $app
                    $existingState = 'mixed_replaced'
                }
            }
            try {
                [System.IO.Directory]::Move($staging, $app)
                if (-not (Test-VerifiedPayload $app)) {
                    throw 'installer_promoted_digest_mismatch'
                }
            }
            catch {
                Remove-OwnedDirectory $app
                if (Test-Path -LiteralPath $backup) {
                    [System.IO.Directory]::Move($backup, $app)
                }
                throw
            }
            $script:candidateRoot = $app
            Write-State 'payload_promoted' $existingState
            Write-Diagnostic 'installer_payload_promotion_pass' 'promote' $app
            Write-Output "installer_payload_transaction_promoted:$existingState"
        }
        'Finalize' {
            $script:candidateRoot = $app
            if (-not (Test-VerifiedPayload $app)) {
                throw 'installer_promoted_digest_mismatch'
            }
            Remove-OwnedDirectory $staging
            Remove-OwnedDirectory $backup
            Write-State 'complete' 'retired'
            Write-Diagnostic 'installer_payload_transaction_pass' 'finalize' $app
            Write-Output 'installer_payload_transaction_finalized'
        }
        'RestoreFailure' {
            if ($FailureCode -notmatch '^installer_[a-z0-9_]+$') {
                throw 'installer_failure_code_invalid'
            }
            $failureResult = Read-InstallerFailureResult $ResultPath
            $FailureCode = [string]$failureResult.code
            $script:candidateRoot = $app
            if (-not (Test-Path -LiteralPath $backup -PathType Container)) {
                throw 'installer_verified_backup_missing'
            }
            if (-not (Test-VerifiedPayload $backup)) {
                throw 'installer_verified_backup_invalid'
            }
            Assert-RollbackDataCompatibility $failureResult $backup $app

            # Preserve evidence for the failed candidate before replacing it.
            Write-Diagnostic $FailureCode 'data_upgrade_failed' $app
            Remove-OwnedDirectory $app
            [System.IO.Directory]::Move($backup, $app)
            if (-not (Test-VerifiedPayload $app)) {
                throw 'installer_restored_payload_digest_mismatch'
            }
            Remove-OwnedDirectory $staging
            $script:candidateRoot = $app
            Write-State 'failed_restored' $FailureCode
            Write-Diagnostic `
                'installer_previous_payload_restored' `
                'restore_failure' `
                $app
            Write-Output "installer_payload_failure_restored:$FailureCode"
        }
        'RecordFailure' {
            if ($FailureCode -notmatch '^installer_[a-z0-9_]+$') {
                throw 'installer_failure_code_invalid'
            }
            $script:candidateRoot = if (Test-Path -LiteralPath $app) {
                $app
            } else {
                $staging
            }
            Write-State 'failed' $FailureCode
            Write-Diagnostic $FailureCode 'failed' $script:candidateRoot
            Write-Output "installer_payload_failure_recorded:$FailureCode"
        }
    }
    exit 0
}
catch {
    $message = [string]$_.Exception.Message
    if ($message -match '^installer_[a-z0-9_]+$') {
        $stableFailure = $message
    }
    try {
        if ($script:productRoot) {
            $payloadRoot = if ($script:candidateRoot) {
                $script:candidateRoot
            } else {
                Join-Path $script:productRoot 'app.__install_staging__'
            }
            Write-Diagnostic $stableFailure $Action.ToLowerInvariant() $payloadRoot
        }
    }
    catch {
        # Diagnostics must never mask the stable installer failure.
    }
    [Console]::Error.WriteLine($stableFailure)
    exit 50
}
