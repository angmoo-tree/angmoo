[CmdletBinding()]
param(
    [string]$Python = "",
    [string]$OutputRoot = ".codex-temp\er6-sidecar-layout-comparison",
    [switch]$FailOnDetection
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $Python) {
    $Python = Join-Path $repoRoot "backend\.venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Pinned backend Python environment is missing: $Python"
}
$output = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $OutputRoot))
New-Item -ItemType Directory -Force -Path $output | Out-Null
$builder = Join-Path $repoRoot "desktop\scripts\build-sidecar.ps1"

function Get-NewDetections([hashtable]$Known) {
    $new = @()
    foreach ($item in @(Get-MpThreatDetection -ErrorAction SilentlyContinue)) {
        $id = [string]$item.DetectionID
        if (-not $Known.ContainsKey($id)) {
            $Known[$id] = $true
            $new += [ordered]@{
                detection_id = $id
                threat_id = [int64]$item.ThreatID
                action_success = [bool]$item.ActionSuccess
            }
        }
    }
    return @($new)
}

function Invoke-DefenderScan([string]$Path) {
    try {
        Start-MpScan -ScanType CustomScan -ScanPath $Path -ErrorAction Stop
        return $null
    }
    catch {
        return $_.Exception.GetType().Name
    }
}

$known = @{}
foreach ($item in @(Get-MpThreatDetection -ErrorAction SilentlyContinue)) {
    $known[[string]$item.DetectionID] = $true
}

$results = @()
foreach ($layout in @("OneFile", "OneDir")) {
    $layoutRoot = Join-Path $output $layout.ToLowerInvariant()
    $buildOutput = @(
        & $builder -Python $Python -WorkRoot $layoutRoot -Layout $layout -DiagnosticOnly 2>&1
    )
    if ($LASTEXITCODE -ne 0) {
        throw "ER6 $layout sidecar comparison build failed: $($buildOutput -join [Environment]::NewLine)"
    }
    $dist = Join-Path $layoutRoot "dist"
    $binary = if ($layout -eq "OneFile") {
        Join-Path $dist "angmoo-sidecar.exe"
    }
    else {
        Join-Path $dist "angmoo-sidecar\angmoo-sidecar.exe"
    }
    if (-not (Test-Path -LiteralPath $binary -PathType Leaf)) {
        throw "ER6 $layout comparison binary is missing: $binary"
    }
    $distributionRoot = if ($layout -eq "OneFile") { $binary } else { Split-Path $binary -Parent }
    $files = if ($layout -eq "OneFile") {
        @(Get-Item -LiteralPath $binary)
    }
    else {
        @(Get-ChildItem -LiteralPath $distributionRoot -Recurse -File)
    }
    $archiveListing = @()
    if ($layout -eq "OneFile") {
        $archiveListing = @(
            & $Python -m PyInstaller.utils.cliutils.archive_viewer -l $binary 2>&1
        )
    }
    else {
        $archiveListing = @($files | ForEach-Object { $_.FullName.Substring($distributionRoot.Length + 1) })
    }
    $legacyDriverEntries = @(
        $archiveListing | Where-Object { [string]$_ -match '(?i)(^|[\\/.])psycopg(?:_binary)?([\\/.]|$)' }
    )
    $scanError = Invoke-DefenderScan $distributionRoot
    Start-Sleep -Seconds 8
    $detections = @(Get-NewDetections $known)
    $results += [ordered]@{
        layout = $layout
        binary_name = [System.IO.Path]::GetFileName($binary)
        binary_bytes = (Get-Item -LiteralPath $binary).Length
        distribution_files = $files.Count
        distribution_bytes = [int64](($files | Measure-Object Length -Sum).Sum)
        binary_sha256 = (Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLowerInvariant()
        explicit_upx_disabled = $true
        legacy_psycopg_entries = $legacyDriverEntries.Count
        scan_error = $scanError
        new_detections = $detections
    }
}

$payload = [ordered]@{
    schema_version = 1
    captured_at = (Get-Date).ToUniversalTime().ToString('o')
    git_commit = (& git -C $repoRoot rev-parse HEAD).Trim()
    results = $results
    selected_release_layout = "OneFile"
    selection_reason = "Tauri externalBin remains one executable; OneDir is diagnostic-only unless its full dependency directory is explicitly bundled."
    privacy = [ordered]@{
        secret_contents_included = $false
        absolute_user_paths_included = $false
        executable_binaries_included = $false
    }
}
$jsonPath = Join-Path $output "er6-sidecar-layout-comparison.json"
$payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $jsonPath -Encoding utf8
$payload | ConvertTo-Json -Depth 8

$detectionCount = @($results | ForEach-Object { $_.new_detections }).Count
if ($FailOnDetection -and $detectionCount -gt 0) {
    throw "ER6 sidecar layout comparison found $detectionCount new Defender detection(s)"
}
