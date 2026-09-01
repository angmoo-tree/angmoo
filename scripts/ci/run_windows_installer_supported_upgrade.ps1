[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Installer,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV1FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV2FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV3FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV4FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$ConflictFixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$Python,
    [Parameter(Mandatory = $true)]
    [string]$Verifier,
    [Parameter(Mandatory = $true)]
    [string]$RunSentinel,
    [ValidateSet('All', 'Upgrade', 'Recovery')]
    [string]$Mode = 'All'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (
    $env:GITHUB_ACTIONS -cne 'true' -or
    $env:RUNNER_ENVIRONMENT -cne 'github-hosted'
) {
    throw 'windows_installer_hosted_runner_only'
}
if (
    [string]::IsNullOrWhiteSpace($env:RUNNER_TEMP) -or
    [string]::IsNullOrWhiteSpace($env:GITHUB_RUN_ID) -or
    [string]::IsNullOrWhiteSpace($env:SOURCE_SHA) -or
    $env:SOURCE_SHA -notmatch '^[0-9a-f]{40}$'
) {
    throw 'windows_installer_hosted_identity_missing'
}
$runnerTemp = [System.IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\')
$sentinelPath = [System.IO.Path]::GetFullPath($RunSentinel)
$sentinelParent = [System.IO.Path]::GetDirectoryName($sentinelPath).TrimEnd('\')
if (-not [string]::Equals(
    $sentinelParent,
    $runnerTemp,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw 'windows_installer_hosted_sentinel_outside_runner_temp'
}
$expectedSentinel = "angmoo-installer-fixture:$($env:GITHUB_RUN_ID):$($env:SOURCE_SHA)"
if (
    -not (Test-Path -LiteralPath $sentinelPath -PathType Leaf) -or
    (Get-Content -LiteralPath $sentinelPath -Raw) -cne $expectedSentinel
) {
    throw 'windows_installer_hosted_sentinel_invalid'
}

foreach ($required in @(
    $Installer,
    $SupportedV1FixtureArchive,
    $SupportedV2FixtureArchive,
    $SupportedV3FixtureArchive,
    $SupportedV4FixtureArchive,
    $ConflictFixtureArchive,
    $Python,
    $Verifier
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "windows_installer_supported_upgrade_input_missing:$required"
    }
}

$productRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $env:LOCALAPPDATA 'Angmoo')
).TrimEnd('\')
$expectedProductRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $env:LOCALAPPDATA 'Angmoo')
).TrimEnd('\')
$legacyRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $env:LOCALAPPDATA 'com.angmoo.desktop')
).TrimEnd('\')
$desktopShortcut = [System.IO.Path]::GetFullPath(
    (Join-Path $env:USERPROFILE 'Desktop\Angmoo.lnk')
)
$startMenuFolder = [System.IO.Path]::GetFullPath(
    (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Angmoo')
).TrimEnd('\')
$startMenuShortcut = Join-Path $startMenuFolder 'Angmoo.lnk'

function Assert-ExactFixtureRoot {
    if (-not [string]::Equals(
        $productRoot,
        $expectedProductRoot,
        [System.StringComparison]::Ordinal
    )) {
        throw 'windows_installer_supported_upgrade_root_invalid'
    }
    if (Test-Path -LiteralPath $productRoot) {
        $item = Get-Item -LiteralPath $productRoot -Force
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'windows_installer_supported_upgrade_reparse_refused'
        }
        $reparse = Get-ChildItem -LiteralPath $productRoot -Force -Recurse |
            Where-Object {
                ($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
            } |
            Select-Object -First 1
        if ($null -ne $reparse) {
            throw 'windows_installer_supported_upgrade_reparse_refused'
        }
    }
}

function Stop-IsolatedProductProcesses {
    Get-Process -Name 'angmoo-desktop', 'angmoo-sidecar' -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
}

function Remove-IsolatedFixture {
    Assert-ExactFixtureRoot
    Stop-IsolatedProductProcesses
    if (Test-Path -LiteralPath $productRoot) {
        Remove-Item -LiteralPath $productRoot -Recurse -Force
    }
    Remove-Item -LiteralPath $desktopShortcut -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $startMenuShortcut -Force -ErrorAction SilentlyContinue
    if (
        (Test-Path -LiteralPath $startMenuFolder -PathType Container) -and
        @(Get-ChildItem -LiteralPath $startMenuFolder -Force).Count -eq 0
    ) {
        Remove-Item -LiteralPath $startMenuFolder -Force
    }
}

function Assert-SyntheticFixtureArchive([string]$Archive) {
    $inspectionRoot = Join-Path `
        $runnerTemp `
        ("angmoo-installer-fixture-inspection-" + [System.Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $inspectionRoot | Out-Null
    Expand-Archive -LiteralPath $Archive -DestinationPath $inspectionRoot
    $manifest = Join-Path $inspectionRoot 'fixture-manifest.json'
    if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
        throw 'windows_installer_supported_upgrade_fixture_manifest_missing'
    }
    $contract = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
    if (
        $contract.synthetic_fixture -ne $true -or
        $contract.contains_real_credentials -ne $false
    ) {
        throw 'windows_installer_supported_upgrade_fixture_not_synthetic'
    }
    $reparse = Get-ChildItem -LiteralPath $inspectionRoot -Force -Recurse |
        Where-Object {
            ($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
        } |
        Select-Object -First 1
    if ($null -ne $reparse) {
        throw 'windows_installer_supported_upgrade_fixture_reparse_refused'
    }
}

function Restore-IsolatedFixture([string]$Archive) {
    # Validate the archive in the ephemeral runner tree before touching the
    # canonical product root. Invalid or non-synthetic input cannot delete data.
    Assert-SyntheticFixtureArchive $Archive
    Remove-IsolatedFixture
    New-Item -ItemType Directory -Force -Path $productRoot | Out-Null
    Expand-Archive -LiteralPath $Archive -DestinationPath $productRoot
    $manifest = Join-Path $productRoot 'fixture-manifest.json'
    if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
        throw 'windows_installer_supported_upgrade_fixture_manifest_missing'
    }
    return $manifest
}

function Invoke-Installer([int]$ExpectedExit) {
    $process = Start-Process `
        -FilePath $Installer `
        -ArgumentList '/S', '/UPDATE' `
        -PassThru
    if (-not $process.WaitForExit(180000)) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        throw 'windows_installer_supported_upgrade_timeout'
    }
    if ($process.ExitCode -ne $ExpectedExit) {
        throw "windows_installer_supported_upgrade_exit_mismatch:$($process.ExitCode):$ExpectedExit"
    }
}

function Invoke-Verifier(
    [string]$Manifest,
    [string]$Status,
    [int]$ExpectedSourceVersion = 0,
    [int]$ExpectedLadybugSourceVersion = 0
) {
    $arguments = @(
        $Verifier,
        '--data-root', $productRoot,
        '--fixture-manifest', $Manifest,
        '--expected-status', $Status
    )
    if ($Status -eq 'upgraded') {
        $arguments += @(
            '--expected-source-version', "$ExpectedSourceVersion",
            '--expected-ladybug-source-version',
            "$ExpectedLadybugSourceVersion"
        )
    }
    & $Python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "windows_installer_supported_upgrade_verifier_failed:$Status"
    }
}

if (Test-Path -LiteralPath $legacyRoot) {
    throw 'windows_installer_supported_upgrade_legacy_root_not_clean'
}

try {
    if ($Mode -in @('All', 'Upgrade')) {
        $supportedManifest = Restore-IsolatedFixture $SupportedV1FixtureArchive
        $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
            ConvertFrom-Json
        Invoke-Installer 0
        Invoke-Verifier `
            $supportedManifest `
            'upgraded' `
            ([int]$supportedContract.source_data_version) `
            ([int]$supportedContract.ladybug_source_data_version)

        $supportedManifest = Restore-IsolatedFixture $SupportedV2FixtureArchive
        $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
            ConvertFrom-Json
        Invoke-Installer 0
        Invoke-Verifier `
            $supportedManifest `
            'upgraded' `
            ([int]$supportedContract.source_data_version) `
            ([int]$supportedContract.ladybug_source_data_version)

        $supportedManifest = Restore-IsolatedFixture $SupportedV3FixtureArchive
        $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
            ConvertFrom-Json
        Invoke-Installer 0
        Invoke-Verifier `
            $supportedManifest `
            'upgraded' `
            ([int]$supportedContract.source_data_version) `
            ([int]$supportedContract.ladybug_source_data_version)

        $supportedManifest = Restore-IsolatedFixture $SupportedV4FixtureArchive
        $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
            ConvertFrom-Json
        Invoke-Installer 0
        Invoke-Verifier `
            $supportedManifest `
            'upgraded' `
            ([int]$supportedContract.source_data_version) `
            ([int]$supportedContract.ladybug_source_data_version)

        # The exact installer must be idempotent after the supported v3 -> v4
        # World-scoped Chat and v4 -> v5 Memory migrations reach the candidate.
        $idempotentPaths = @(
            (Join-Path $productRoot 'canonical\current-generation.json'),
            (Join-Path $productRoot 'canonical\previous-generation.json'),
            (Join-Path $productRoot 'graph\current-generation.json'),
            (Join-Path $productRoot 'graph\previous-generation.json')
        )
        $idempotentHashes = @{}
        foreach ($path in $idempotentPaths) {
            $idempotentHashes[$path] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
        }
        $canonicalGenerations = @(
            Get-ChildItem -LiteralPath (Join-Path $productRoot 'canonical\generations') `
                -Directory -Force | Sort-Object Name | Select-Object -ExpandProperty Name
        ) -join "`n"
        $graphGenerations = @(
            Get-ChildItem -LiteralPath (Join-Path $productRoot 'graph\generations') `
                -Directory -Force | Sort-Object Name | Select-Object -ExpandProperty Name
        ) -join "`n"
        $candidatePayload = Get-Content `
            -LiteralPath (Join-Path $productRoot 'app\installer-payload.json') `
            -Raw | ConvertFrom-Json
        Invoke-Installer 0
        Invoke-Verifier `
            $supportedManifest `
            'upgraded' `
            ([int]$candidatePayload.embedded_data.sqlite.target_version) `
            ([int]$candidatePayload.embedded_data.ladybug.target_version)
        foreach ($path in $idempotentPaths) {
            $actualHash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
            if ($actualHash -cne $idempotentHashes[$path]) {
                throw "windows_installer_idempotent_marker_changed:$path"
            }
        }
        $actualCanonicalGenerations = @(
            Get-ChildItem -LiteralPath (Join-Path $productRoot 'canonical\generations') `
                -Directory -Force | Sort-Object Name | Select-Object -ExpandProperty Name
        ) -join "`n"
        $actualGraphGenerations = @(
            Get-ChildItem -LiteralPath (Join-Path $productRoot 'graph\generations') `
                -Directory -Force | Sort-Object Name | Select-Object -ExpandProperty Name
        ) -join "`n"
        if ($actualCanonicalGenerations -cne $canonicalGenerations) {
            throw 'windows_installer_idempotent_sqlite_generation_created'
        }
        if ($actualGraphGenerations -cne $graphGenerations) {
            throw 'windows_installer_idempotent_ladybug_generation_created'
        }
        Write-Output 'windows_installer_supported_upgrade_matrix_pass'
    }

    if ($Mode -in @('All', 'Recovery')) {
        $conflictManifest = Restore-IsolatedFixture $ConflictFixtureArchive
        Invoke-Installer 42
        Invoke-Verifier $conflictManifest 'restored'
        Write-Output 'windows_installer_failure_recovery_matrix_pass'
    }

    Write-Output 'windows_installer_supported_upgrade_and_recovery_matrix_pass'
}
finally {
    Remove-IsolatedFixture
}

exit 0
