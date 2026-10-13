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
    [string]$SupportedV5FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV6FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV7FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV8FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV9FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV10FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV11FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV12FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV13FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV14FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV15FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV16FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV17FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV18FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV19FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV20FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV21FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV22FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV23FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV24FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV25FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV26FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV27FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV28FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV29FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV30FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV31FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV32FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV33FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV34FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV35FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$SupportedV36FixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$ConflictFixtureArchive,
    [Parameter(Mandatory = $true)]
    [string]$Python,
    [Parameter(Mandatory = $true)]
    [string]$Verifier,
    [Parameter(Mandatory = $true)]
    [string]$RunSentinel,
    [ValidateSet('all', 'first', 'second')]
    [string]$UpgradePartition = 'all',
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

$coverageTool = Join-Path $PSScriptRoot 'windows_installer_upgrade_coverage.py'

foreach ($required in @(
    $Installer,
    $SupportedV1FixtureArchive,
    $SupportedV2FixtureArchive,
    $SupportedV3FixtureArchive,
    $SupportedV4FixtureArchive,
    $SupportedV5FixtureArchive,
    $SupportedV6FixtureArchive,
    $SupportedV7FixtureArchive,
    $SupportedV8FixtureArchive,
    $SupportedV9FixtureArchive,
    $SupportedV10FixtureArchive,
    $SupportedV11FixtureArchive,
    $SupportedV12FixtureArchive,
    $SupportedV13FixtureArchive,
    $SupportedV14FixtureArchive,
    $SupportedV15FixtureArchive,
    $SupportedV16FixtureArchive,
    $SupportedV17FixtureArchive,
    $SupportedV18FixtureArchive,
    $SupportedV19FixtureArchive,
    $SupportedV20FixtureArchive,
    $SupportedV21FixtureArchive,
    $SupportedV22FixtureArchive,
    $SupportedV23FixtureArchive,
    $SupportedV24FixtureArchive,
    $SupportedV25FixtureArchive,
    $SupportedV26FixtureArchive,
    $SupportedV27FixtureArchive,
    $SupportedV28FixtureArchive,
    $SupportedV29FixtureArchive,
    $SupportedV30FixtureArchive,
    $SupportedV31FixtureArchive,
    $SupportedV32FixtureArchive,
    $SupportedV33FixtureArchive,
    $SupportedV34FixtureArchive,
    $SupportedV35FixtureArchive,
    $SupportedV36FixtureArchive,
    $ConflictFixtureArchive,
    $Python,
    $Verifier,
    $coverageTool
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
        # This script is restricted to sentinel-verified synthetic runner data.
        # Preserve only the stable failure code before fixture cleanup; never
        # dump the result body, paths, database contents, or credentials.
        $resultPath = Join-Path $productRoot 'runtime\installer-data-upgrade-result.json'
        if (Test-Path -LiteralPath $resultPath -PathType Leaf) {
            $result = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
            if ($result.code -cmatch '^[a-z0-9_]{1,100}$') {
                Write-Output "windows_installer_supported_upgrade_failure_code:$($result.code)"
            }
        }
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
        $selectedJson = & $Python $coverageTool --select-partition $UpgradePartition
        if ($LASTEXITCODE -ne 0) { throw 'windows_installer_partition_selection_failed' }
        $selectedVersions = @($selectedJson | ConvertFrom-Json)
        if ($selectedVersions.Count -eq 0) { throw 'windows_installer_empty_partition' }
        $completedVersions = [System.Collections.Generic.List[int]]::new()
        if ($selectedVersions -contains 1) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV1FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 1) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(1)
            Write-Output "windows_installer_supported_predecessor_verified:v1"
        }

        if ($selectedVersions -contains 2) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV2FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 2) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(2)
            Write-Output "windows_installer_supported_predecessor_verified:v2"
        }

        if ($selectedVersions -contains 3) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV3FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 3) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(3)
            Write-Output "windows_installer_supported_predecessor_verified:v3"
        }

        if ($selectedVersions -contains 4) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV4FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 4) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(4)
            Write-Output "windows_installer_supported_predecessor_verified:v4"
        }

        if ($selectedVersions -contains 5) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV5FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 5) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(5)
            Write-Output "windows_installer_supported_predecessor_verified:v5"
        }

        if ($selectedVersions -contains 6) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV6FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 6) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(6)
            Write-Output "windows_installer_supported_predecessor_verified:v6"
        }

        if ($selectedVersions -contains 7) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV7FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 7) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(7)
            Write-Output "windows_installer_supported_predecessor_verified:v7"
        }

        if ($selectedVersions -contains 8) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV8FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 8) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(8)
            Write-Output "windows_installer_supported_predecessor_verified:v8"
        }

        if ($selectedVersions -contains 9) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV9FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 9) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(9)
            Write-Output "windows_installer_supported_predecessor_verified:v9"
        }

        if ($selectedVersions -contains 10) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV10FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 10) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(10)
            Write-Output "windows_installer_supported_predecessor_verified:v10"
        }

        if ($selectedVersions -contains 11) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV11FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 11) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(11)
            Write-Output "windows_installer_supported_predecessor_verified:v11"
        }

        if ($selectedVersions -contains 12) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV12FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 12) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(12)
            Write-Output "windows_installer_supported_predecessor_verified:v12"
        }

        if ($selectedVersions -contains 13) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV13FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 13) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(13)
            Write-Output "windows_installer_supported_predecessor_verified:v13"
        }

        if ($selectedVersions -contains 14) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV14FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 14) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(14)
            Write-Output "windows_installer_supported_predecessor_verified:v14"
        }

        if ($selectedVersions -contains 15) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV15FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 15) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(15)
            Write-Output "windows_installer_supported_predecessor_verified:v15"
        }

        if ($selectedVersions -contains 16) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV16FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 16) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(16)
            Write-Output "windows_installer_supported_predecessor_verified:v16"
        }

        if ($selectedVersions -contains 17) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV17FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 17) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(17)
            Write-Output "windows_installer_supported_predecessor_verified:v17"
        }

        if ($selectedVersions -contains 18) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV18FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 18) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(18)
            Write-Output "windows_installer_supported_predecessor_verified:v18"
        }

        if ($selectedVersions -contains 19) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV19FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 19) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(19)
            Write-Output "windows_installer_supported_predecessor_verified:v19"
        }

        if ($selectedVersions -contains 20) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV20FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 20) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(20)
            Write-Output "windows_installer_supported_predecessor_verified:v20"
        }

        if ($selectedVersions -contains 21) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV21FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 21) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(21)
            Write-Output "windows_installer_supported_predecessor_verified:v21"
        }

        if ($selectedVersions -contains 22) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV22FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 22) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(22)
            Write-Output "windows_installer_supported_predecessor_verified:v22"
        }

        if ($selectedVersions -contains 23) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV23FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 23) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(23)
            Write-Output "windows_installer_supported_predecessor_verified:v23"
        }

        if ($selectedVersions -contains 24) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV24FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 24) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(24)
            Write-Output "windows_installer_supported_predecessor_verified:v24"
        }

        if ($selectedVersions -contains 25) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV25FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 25) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(25)
            Write-Output "windows_installer_supported_predecessor_verified:v25"
        }

        if ($selectedVersions -contains 26) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV26FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 26) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(26)
            Write-Output "windows_installer_supported_predecessor_verified:v26"
        }

        if ($selectedVersions -contains 27) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV27FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 27) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(27)
            Write-Output "windows_installer_supported_predecessor_verified:v27"
        }

        if ($selectedVersions -contains 28) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV28FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 28) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(28)
            Write-Output "windows_installer_supported_predecessor_verified:v28"
        }

        if ($selectedVersions -contains 29) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV29FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 29) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(29)
            Write-Output "windows_installer_supported_predecessor_verified:v29"
        }

        if ($selectedVersions -contains 30) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV30FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 30) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(30)
            Write-Output "windows_installer_supported_predecessor_verified:v30"
        }

        if ($selectedVersions -contains 31) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV31FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 31) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(31)
            Write-Output "windows_installer_supported_predecessor_verified:v31"
        }

        if ($selectedVersions -contains 32) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV32FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 32) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(32)
            Write-Output "windows_installer_supported_predecessor_verified:v32"
        }

        if ($selectedVersions -contains 33) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV33FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 33) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(33)
            Write-Output "windows_installer_supported_predecessor_verified:v33"
        }

        if ($selectedVersions -contains 34) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV34FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 34) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(34)
            Write-Output "windows_installer_supported_predecessor_verified:v34"
        }

        if ($selectedVersions -contains 35) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV35FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 35) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(35)
            Write-Output "windows_installer_supported_predecessor_verified:v35"
        }

        if ($selectedVersions -contains 36) {
            $supportedManifest = Restore-IsolatedFixture $SupportedV36FixtureArchive
            $supportedContract = Get-Content -LiteralPath $supportedManifest -Raw |
                ConvertFrom-Json
            if ([int]$supportedContract.source_data_version -ne 36) {
                throw 'windows_installer_selected_predecessor_mismatch'
            }
            Invoke-Installer 0
            Invoke-Verifier `
                $supportedManifest `
                'upgraded' `
                ([int]$supportedContract.source_data_version) `
                ([int]$supportedContract.ladybug_source_data_version)
            $completedVersions.Add(36)
            Write-Output "windows_installer_supported_predecessor_verified:v36"
        }

        # The exact installer must be idempotent after the supported v3 -> v4
        # World-scoped Chat, v4 -> v5 Memory, and v5 -> v6 response lifecycle
        # migrations reach the candidate.
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
        if (($completedVersions -join ',') -cne ($selectedVersions -join ',')) {
            throw 'windows_installer_partition_coverage_incomplete'
        }
        if ($env:GITHUB_RUN_ATTEMPT -notmatch '^[1-9][0-9]*$') {
            throw 'windows_installer_upgrade_attempt_missing'
        }
        $receiptPath = Join-Path $runnerTemp "angmoo-supported-upgrade-$UpgradePartition.json"
        @{
            schema = 'windows-installer-upgrade-coverage.v1'
            status = 'completed'
            source_sha = $env:SOURCE_SHA
            run_id = $env:GITHUB_RUN_ID
            run_attempt = $env:GITHUB_RUN_ATTEMPT
            partition = $UpgradePartition
            versions = @($completedVersions.ToArray())
            idempotent = $true
        } | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $receiptPath -Encoding utf8
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
