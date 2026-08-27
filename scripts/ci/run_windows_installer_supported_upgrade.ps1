[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Installer,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV1FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV2FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$ConflictFixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$Python,
    [Parameter(Mandatory = $true)]
    [string]$Verifier,
    [ValidateSet('All', 'Upgrade', 'Recovery')]
    [string]$Mode = 'All'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

foreach ($required in @(
    $Installer,
    $SupportedV1FixtureArchive,
    $SupportedV2FixtureArchive,
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

function Restore-IsolatedFixture([string]$Archive) {
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
    [int]$ExpectedSourceVersion = 0
) {
    $arguments = @(
        $Verifier,
        '--data-root', $productRoot,
        '--fixture-manifest', $Manifest,
        '--expected-status', $Status
    )
    if ($Status -eq 'upgraded') {
        $arguments += @('--expected-source-version', "$ExpectedSourceVersion")
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
        Invoke-Installer 0
        Invoke-Verifier $supportedManifest 'upgraded' 1

        $supportedManifest = Restore-IsolatedFixture $SupportedV2FixtureArchive
        Invoke-Installer 0
        Invoke-Verifier $supportedManifest 'upgraded' 2

        # The exact installer must be idempotent after the first v2 -> v3 update.
        Invoke-Installer 0
        Invoke-Verifier $supportedManifest 'upgraded' 3
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
