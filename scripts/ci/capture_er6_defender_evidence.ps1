[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputRoot,
    [string]$DataRoot = (Join-Path $env:LOCALAPPDATA 'com.angmoo.desktop'),
    [string[]]$CandidatePaths = @()
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$output = [System.IO.Path]::GetFullPath($OutputRoot)
New-Item -ItemType Directory -Force -Path $output | Out-Null

function Get-FileEvidence([string]$Label, [string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return [ordered]@{ label = $Label; present = $false }
    }
    $file = Get-Item -LiteralPath $Path
    return [ordered]@{
        label = $Label
        present = $true
        file_name = $file.Name
        bytes = $file.Length
        sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

function Convert-DefenderResource([string]$Resource) {
    $normalized = $Resource -replace '\\', '/'
    if ($normalized -match '(?i)angmoo-desktop\.exe') { return 'installed_host' }
    if ($normalized -match '(?i)angmoo-sidecar\.exe') { return 'installed_sidecar' }
    if ($normalized -match '(?i)Angmoo\.lnk') { return 'start_menu_shortcut' }
    if ($normalized -match '(?i)CURRENTVERSION/UNINSTALL/Angmoo') { return 'uninstall_registration' }
    return 'redacted_other_resource'
}

$status = Get-MpComputerStatus | Select-Object `
    AntivirusEnabled, RealTimeProtectionEnabled, BehaviorMonitorEnabled, `
    AMEngineVersion, AMProductVersion, AntivirusSignatureVersion, `
    AntivirusSignatureLastUpdated
$threatNames = @{}
foreach ($threat in @(Get-MpThreat -ErrorAction SilentlyContinue)) {
    $threatNames[[string]$threat.ThreatID] = $threat.ThreatName
}
$detections = @(
    Get-MpThreatDetection -ErrorAction SilentlyContinue |
        Where-Object { $_.ThreatID -eq 2147731250 } |
        Sort-Object InitialDetectionTime |
        ForEach-Object {
            [ordered]@{
                detection_id = [string]$_.DetectionID
                threat_id = [int64]$_.ThreatID
                threat_name = $threatNames[[string]$_.ThreatID]
                initial_detection_time = $_.InitialDetectionTime.ToString('o')
                remediation_time = if ($_.RemediationTime) { $_.RemediationTime.ToString('o') } else { $null }
                detection_source_type_id = $_.DetectionSourceTypeID
                cleaning_action_id = $_.CleaningActionID
                action_success = [bool]$_.ActionSuccess
                resources = @($_.Resources | ForEach-Object { Convert-DefenderResource ([string]$_) } | Sort-Object -Unique)
            }
        }
)

$candidates = @()
foreach ($candidate in $CandidatePaths) {
    $candidates += Get-FileEvidence ('candidate_' + [System.IO.Path]::GetFileName($candidate)) $candidate
}
$canonical = @(
    Get-FileEvidence 'sqlite_canonical' (Join-Path $DataRoot 'canonical\generations\er6-preview-v1\angmoo.sqlite3')
    Get-FileEvidence 'ladybug_projection' (Join-Path $DataRoot 'graph\ladybug\relationships.lbdb')
    Get-FileEvidence 'app_secret_hash_only' (Join-Path $DataRoot 'secrets\app-secret')
)
$locks = @(
    Get-FileEvidence 'backend_uv_lock' (Join-Path $repoRoot 'backend\uv.lock')
    Get-FileEvidence 'frontend_pnpm_lock' (Join-Path $repoRoot 'frontend\pnpm-lock.yaml')
    Get-FileEvidence 'desktop_package_lock' (Join-Path $repoRoot 'desktop\package-lock.json')
    Get-FileEvidence 'desktop_cargo_lock' (Join-Path $repoRoot 'desktop\src-tauri\Cargo.lock')
)
$gitCommit = (& git -C $repoRoot rev-parse HEAD).Trim()
$payload = [ordered]@{
    schema_version = 1
    captured_at = (Get-Date).ToUniversalTime().ToString('o')
    git_commit = $gitCommit
    defender = $status
    detections = $detections
    candidates = $candidates
    canonical_data_hashes = $canonical
    dependency_lock_hashes = $locks
    privacy = [ordered]@{
        secret_contents_included = $false
        absolute_user_paths_included = $false
        executable_binaries_included = $false
    }
}
$jsonPath = Join-Path $output 'er6-defender-local-evidence.json'
$payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $jsonPath -Encoding utf8
$hash = (Get-FileHash -LiteralPath $jsonPath -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath (Join-Path $output 'SHA256SUMS') -Value "$hash  er6-defender-local-evidence.json" -Encoding ascii
Write-Output $jsonPath
