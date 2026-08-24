[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$MinimalHost,
    [Parameter(Mandatory = $true)]
    [string]$StubHost,
    [Parameter(Mandatory = $true)]
    [string]$RealSidecarHost,
    [Parameter(Mandatory = $true)]
    [string]$StubSidecar,
    [Parameter(Mandatory = $true)]
    [string]$ActualHost,
    [Parameter(Mandatory = $true)]
    [string]$ActualSidecar,
    [Parameter(Mandatory = $true)]
    [string]$Installer,
    [Parameter(Mandatory = $true)]
    [string]$OutputRoot,
    [switch]$SkipBehaviorMatrix,
    [switch]$InstallCandidate,
    [switch]$ExerciseInstalledRuntime,
    [switch]$FailOnDetection
)

$ErrorActionPreference = 'Stop'
$output = [System.IO.Path]::GetFullPath($OutputRoot)
$work = Join-Path $output ('work-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $work | Out-Null

$requiredInputs = @($ActualHost, $ActualSidecar, $Installer)
if (-not $SkipBehaviorMatrix) {
    $requiredInputs += @($MinimalHost, $StubHost, $RealSidecarHost, $StubSidecar)
}
foreach ($required in $requiredInputs) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "ER6 Defender matrix input is missing: $required"
    }
}

$knownDetectionIds = @{}
foreach ($item in @(Get-MpThreatDetection -ErrorAction SilentlyContinue)) {
    $knownDetectionIds[[string]$item.DetectionID] = $true
}

function Convert-ResourceRole([string]$Resource) {
    if ($Resource -match '(?i)matrix-host') { return 'matrix_host' }
    if ($Resource -match '(?i)matrix-stub') { return 'matrix_stub' }
    if ($Resource -match '(?i)angmoo-desktop\.exe') { return 'angmoo_host' }
    if ($Resource -match '(?i)angmoo-sidecar\.exe') { return 'angmoo_sidecar' }
    if ($Resource -match '(?i)setup.*\.exe') { return 'nsis_installer' }
    if ($Resource -match '(?i)Angmoo\.lnk') { return 'start_menu_shortcut' }
    if ($Resource -match '(?i)CURRENTVERSION\\UNINSTALL\\Angmoo') { return 'uninstall_registration' }
    return 'redacted_other_resource'
}

function Get-NewDetectionEvidence {
    $new = @()
    foreach ($item in @(Get-MpThreatDetection -ErrorAction SilentlyContinue)) {
        $id = [string]$item.DetectionID
        if (-not $knownDetectionIds.ContainsKey($id)) {
            $knownDetectionIds[$id] = $true
            $new += [ordered]@{
                detection_id = $id
                threat_id = [int64]$item.ThreatID
                initial_detection_time = $item.InitialDetectionTime.ToString('o')
                detection_source_type_id = $item.DetectionSourceTypeID
                cleaning_action_id = $item.CleaningActionID
                action_success = [bool]$item.ActionSuccess
                resources = @($item.Resources | ForEach-Object { Convert-ResourceRole ([string]$_) } | Sort-Object -Unique)
            }
        }
    }
    return @($new)
}

function Get-Manifest([string[]]$Paths) {
    $manifest = @()
    foreach ($path in $Paths) {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            try {
                $file = Get-Item -LiteralPath $path
                $manifest += [ordered]@{
                    file_name = $file.Name
                    bytes = $file.Length
                    sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
                    readable = $true
                }
            }
            catch {
                # Defender can quarantine or deny a file between Test-Path and
                # hashing. That transition is matrix evidence, not a reason to
                # lose the remainder of the stage report.
                $manifest += [ordered]@{
                    file_name = [System.IO.Path]::GetFileName($path)
                    bytes = $null
                    sha256 = $null
                    readable = $false
                    read_error = $_.Exception.GetType().Name
                }
            }
        }
    }
    return @($manifest)
}

function Start-IsolatedProcess(
    [string]$FilePath,
    [string[]]$Arguments,
    [hashtable]$Environment
) {
    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $FilePath
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    foreach ($argument in $Arguments) {
        $start.ArgumentList.Add($argument)
    }
    foreach ($entry in $Environment.GetEnumerator()) {
        $start.Environment[[string]$entry.Key] = [string]$entry.Value
    }
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $start
    if (-not $process.Start()) { throw "failed to start matrix process: $FilePath" }
    return $process
}

function Stop-IsolatedProcess([System.Diagnostics.Process]$Process) {
    if ($Process.HasExited) { return }
    $null = $Process.CloseMainWindow()
    if (-not $Process.WaitForExit(10000)) {
        $Process.Kill($true)
        $Process.WaitForExit(5000) | Out-Null
    }
}

$scanFallbacks = @()

function Invoke-CustomScan([string[]]$Paths) {
    $errors = @()
    foreach ($path in $Paths) {
        if (-not (Test-Path -LiteralPath $path)) {
            $errors += "missing_before_scan:$([System.IO.Path]::GetFileName($path))"
            continue
        }
        try {
            Start-MpScan -ScanType CustomScan -ScanPath $path -ErrorAction Stop
        }
        catch {
            $startMpScanError = $_.Exception.Message
            $directoryFallbackSucceeded = $false
            if (Test-Path -LiteralPath $path -PathType Leaf) {
                # Some Defender builds reject a large individual NSIS archive
                # with 0x80508023 while accepting a custom scan of the exact
                # directory that contains it. The bundle/nsis directory has a
                # single release candidate, so this is still a bounded scan.
                $parent = [System.IO.Path]::GetDirectoryName(
                    [System.IO.Path]::GetFullPath($path)
                )
                try {
                    Start-MpScan -ScanType CustomScan -ScanPath $parent -ErrorAction Stop
                    $directoryFallbackSucceeded = $true
                    $script:scanFallbacks += [ordered]@{
                        file_name = [System.IO.Path]::GetFileName($path)
                        method = 'parent_directory_custom_scan'
                        direct_scan_error = $startMpScanError
                    }
                }
                catch {
                    $directoryFallbackSucceeded = $false
                }
            }
            if ($directoryFallbackSucceeded) { continue }

            # Start-MpScan occasionally refuses a large NSIS file while the
            # Defender service is otherwise healthy. MpCmdRun is Microsoft's
            # supported command-line scanner and provides a deterministic
            # fallback without disabling remediation or adding an exclusion.
            $platformRoot = Join-Path $env:ProgramData 'Microsoft\Windows Defender\Platform'
            $mpCmdRun = $null
            if (Test-Path -LiteralPath $platformRoot) {
                $mpCmdRun = Get-ChildItem -LiteralPath $platformRoot -Directory |
                    Sort-Object Name -Descending |
                    ForEach-Object { Join-Path $_.FullName 'MpCmdRun.exe' } |
                    Where-Object { Test-Path -LiteralPath $_ } |
                    Select-Object -First 1
            }
            if (-not $mpCmdRun) {
                $mpCmdRun = Join-Path $env:ProgramFiles 'Windows Defender\MpCmdRun.exe'
            }
            $fallbackOutput = @(& $mpCmdRun -Scan -ScanType 3 -File $path -ReturnHR 2>&1)
            if ($LASTEXITCODE -ne 0) {
                $summary = ($fallbackOutput | Select-Object -Last 3) -join ' '
                $errors += (
                    "scan_error:{0}:Start-MpScan={1};MpCmdRun={2}:{3}" -f
                    [System.IO.Path]::GetFileName($path),
                    $startMpScanError,
                    $LASTEXITCODE,
                    $summary
                )
            }
        }
    }
    return @($errors)
}

function Complete-Stage(
    [string]$Name,
    [string[]]$Paths,
    [string[]]$ScanErrors,
    [hashtable]$Runtime = @{}
) {
    Start-Sleep -Seconds 6
    $detections = @(Get-NewDetectionEvidence)
    return [ordered]@{
        name = $Name
        inputs = Get-Manifest $Paths
        scan_errors = @($ScanErrors)
        files_present_after = @($Paths | ForEach-Object {
            [ordered]@{ file_name = [System.IO.Path]::GetFileName($_); present = [bool](Test-Path -LiteralPath $_) }
        })
        runtime = $Runtime
        new_detections = $detections
        detected = ($detections.Count -gt 0)
    }
}

$stages = @()

if (-not $SkipBehaviorMatrix) {
# 1. Minimal Tauri host, no sidecar present or executed.
$stage1 = Join-Path $work '01-minimal-host'
New-Item -ItemType Directory -Force -Path $stage1 | Out-Null
$stage1Host = Join-Path $stage1 'angmoo-defender-matrix-host.exe'
Copy-Item -LiteralPath $MinimalHost -Destination $stage1Host
$errors = @(Invoke-CustomScan @($stage1Host))
$process = Start-IsolatedProcess $stage1Host @() @{}
$exited = $process.WaitForExit(15000)
if (-not $exited) { Stop-IsolatedProcess $process }
$stages += Complete-Stage '01_minimal_tauri_host' @($stage1Host) $errors @{ host_exited = $exited }

# 2. Real sidecar is adjacent, but the minimal host has no code path that starts it.
$stage2 = Join-Path $work '02-bundled-not-executed'
New-Item -ItemType Directory -Force -Path $stage2 | Out-Null
$stage2Host = Join-Path $stage2 'angmoo-defender-matrix-host.exe'
$stage2Sidecar = Join-Path $stage2 'angmoo-sidecar.exe'
Copy-Item -LiteralPath $MinimalHost -Destination $stage2Host
Copy-Item -LiteralPath $ActualSidecar -Destination $stage2Sidecar
$beforeSidecars = @(Get-Process -Name 'angmoo-sidecar' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
$errors = @(Invoke-CustomScan @($stage2))
$process = Start-IsolatedProcess $stage2Host @() @{}
$exited = $process.WaitForExit(15000)
if (-not $exited) { Stop-IsolatedProcess $process }
$newSidecars = @(Get-Process -Name 'angmoo-sidecar' -ErrorAction SilentlyContinue | Where-Object Id -notin $beforeSidecars)
foreach ($unexpected in $newSidecars) { Stop-Process -Id $unexpected.Id -Force -ErrorAction SilentlyContinue }
$stages += Complete-Stage '02_real_sidecar_adjacent_not_executed' @($stage2Host, $stage2Sidecar) $errors @{
    host_exited = $exited
    unexpected_real_sidecar_processes = $newSidecars.Count
}

# 3. Minimal host starts one inert Rust child and exits normally.
$stage3 = Join-Path $work '03-stub-child'
New-Item -ItemType Directory -Force -Path $stage3 | Out-Null
$stage3Host = Join-Path $stage3 'angmoo-defender-matrix-stub-host.exe'
$stage3Stub = Join-Path $stage3 'angmoo-defender-matrix-stub.exe'
$marker = Join-Path $stage3 'stub-started.marker'
Copy-Item -LiteralPath $StubHost -Destination $stage3Host
Copy-Item -LiteralPath $StubSidecar -Destination $stage3Stub
$errors = @(Invoke-CustomScan @($stage3))
$process = Start-IsolatedProcess $stage3Host @() @{
    ANGMOO_DEFENDER_MATRIX_STUB = $stage3Stub
    ANGMOO_DEFENDER_MATRIX_MARKER = $marker
}
$deadline = (Get-Date).AddSeconds(12)
while ((Get-Date) -lt $deadline -and -not (Test-Path -LiteralPath $marker)) {
    Start-Sleep -Milliseconds 250
}
$markerCreated = Test-Path -LiteralPath $marker
$exited = $process.WaitForExit(15000)
if (-not $exited) { Stop-IsolatedProcess $process }
$stages += Complete-Stage '03_minimal_stub_child_execution' @($stage3Host, $stage3Stub) $errors @{
    host_exited = $exited
    stub_started = $markerCreated
}

# 4a. The production Tauri host is copied to an inert location and scanned,
# but not executed. This separates file reputation from NSIS registration and
# installed-path context without touching canonical user data.
$stage4a = Join-Path $work '04a-product-host-static'
New-Item -ItemType Directory -Force -Path $stage4a | Out-Null
$stage4aHost = Join-Path $stage4a 'angmoo-desktop.exe'
Copy-Item -LiteralPath $ActualHost -Destination $stage4aHost
$errors = @(Invoke-CustomScan @($stage4aHost))
$stages += Complete-Stage '04a_product_host_static_copy_not_executed' @($stage4aHost) $errors @{
    product_executed = $false
    canonical_user_data_used = $false
}

# 4. A dedicated host starts the real PyInstaller sidecar with the reviewed
# data-root, legacy-root, runtime-root, launch-id, typed runtime-profile, and
# loopback token contract. Supplying the isolated data root directly keeps this
# stage separate from canonical user data.
$stage4 = Join-Path $work '04-real-runtime'
$stage4RuntimeRoot = Join-Path $stage4 'isolated-data\runtime'
New-Item -ItemType Directory -Force -Path $stage4,$stage4RuntimeRoot | Out-Null
$stage4Host = Join-Path $stage4 'angmoo-defender-matrix-real-host.exe'
$stage4Sidecar = Join-Path $stage4 'angmoo-sidecar.exe'
Copy-Item -LiteralPath $RealSidecarHost -Destination $stage4Host
Copy-Item -LiteralPath $ActualSidecar -Destination $stage4Sidecar
$errors = @(Invoke-CustomScan @($stage4))
$process = $null
$runtimeReady = $false
$endpoint = Join-Path $stage4RuntimeRoot 'sidecar.endpoint.json'
if ((Test-Path -LiteralPath $stage4Host) -and (Test-Path -LiteralPath $stage4Sidecar)) {
    $process = Start-IsolatedProcess $stage4Host @() @{
        ANGMOO_DEFENDER_MATRIX_REAL_SIDECAR = $stage4Sidecar
        ANGMOO_DEFENDER_MATRIX_RUNTIME_ROOT = $stage4RuntimeRoot
    }
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline -and -not (Test-Path -LiteralPath $endpoint)) {
        Start-Sleep -Milliseconds 500
    }
    $runtimeReady = Test-Path -LiteralPath $endpoint
    Stop-IsolatedProcess $process
}
$stages += Complete-Stage '04_real_pyinstaller_sidecar_execution' @($stage4Host, $stage4Sidecar) $errors @{
    runtime_endpoint_created = $runtimeReady
    isolated_data_root = $true
    product_host_sha256 = (Get-FileHash -LiteralPath $ActualHost -Algorithm SHA256).Hash.ToLowerInvariant()
}
}

# 5. Full NSIS installer as a file, before installation.
$errors = @(Invoke-CustomScan @($Installer))
$stages += Complete-Stage '05_full_nsis_installer' @($Installer) $errors @{}

if ($InstallCandidate) {
    $install = Start-Process -FilePath $Installer -ArgumentList '/S' -PassThru
    if (-not $install.WaitForExit(180000)) {
        Stop-Process -Id $install.Id -Force -ErrorAction SilentlyContinue
        throw 'ER6 matrix NSIS install timed out'
    }
    Start-Sleep -Seconds 10
    $installRoot = Join-Path $env:LOCALAPPDATA 'Angmoo\app'
    $installedHost = Join-Path $installRoot 'angmoo-desktop.exe'
    $installedSidecar = Join-Path $installRoot 'angmoo-sidecar.exe'

    # 6. Installed production host.
    $errors = @(Invoke-CustomScan @($installedHost))
    $stages += Complete-Stage '06_installed_angmoo_host' @($installedHost) $errors @{}

    # 7. Installed production sidecar.
    $errors = @(Invoke-CustomScan @($installedSidecar))
    $stages += Complete-Stage '07_installed_angmoo_sidecar' @($installedSidecar) $errors @{}

    # 8. Entire install directory. Product execution is optional here because
    # a normal Tauri host resolves Windows KnownFolder paths independently of
    # a child-process LOCALAPPDATA override. CI uses an ephemeral runner and
    # exercises the installed runtime in its dedicated smoke job.
    $errors = @(Invoke-CustomScan @($installRoot))
    $installedRuntimeReady = $false
    if ($ExerciseInstalledRuntime -and (Test-Path -LiteralPath $installedHost) -and (Test-Path -LiteralPath $installedSidecar)) {
        $process = Start-IsolatedProcess $installedHost @() @{}
        $installedEndpoint = Join-Path $env:LOCALAPPDATA 'Angmoo\runtime\sidecar.endpoint.json'
        $deadline = (Get-Date).AddSeconds(60)
        while ((Get-Date) -lt $deadline -and -not (Test-Path -LiteralPath $installedEndpoint)) {
            Start-Sleep -Milliseconds 500
        }
        $installedRuntimeReady = Test-Path -LiteralPath $installedEndpoint
        Stop-IsolatedProcess $process
    }
    $stages += Complete-Stage '08_installed_directory_and_runtime' @($installRoot) $errors @{
        runtime_endpoint_created = $installedRuntimeReady
        runtime_exercised = [bool]$ExerciseInstalledRuntime
    }
}

$status = Get-MpComputerStatus | Select-Object AntivirusEnabled, RealTimeProtectionEnabled, `
    BehaviorMonitorEnabled, AMEngineVersion, AMProductVersion, `
    AntivirusSignatureVersion, AntivirusSignatureLastUpdated
$payload = [ordered]@{
    schema_version = 1
    captured_at = (Get-Date).ToUniversalTime().ToString('o')
    defender = $status
    install_candidate_exercised = [bool]$InstallCandidate
    behavior_matrix_exercised = [bool](-not $SkipBehaviorMatrix)
    stages = $stages
    detection_count = @($stages | ForEach-Object { $_.new_detections }).Count
    scan_error_count = @($stages | ForEach-Object { $_.scan_errors }).Count
    scan_fallbacks = @($scanFallbacks)
    privacy = [ordered]@{
        canonical_user_data_used = [bool]($InstallCandidate -and $ExerciseInstalledRuntime)
        secret_contents_included = $false
        absolute_user_paths_included = $false
        executable_binaries_included = $false
    }
}
$jsonPath = Join-Path $output 'er6-defender-trigger-matrix.json'
$payload | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $jsonPath -Encoding utf8
$payload | ConvertTo-Json -Depth 10
if ($FailOnDetection -and $payload.detection_count -gt 0) {
    throw "ER6 Defender trigger matrix found $($payload.detection_count) new detection(s)"
}
if ($FailOnDetection -and $payload.scan_error_count -gt 0) {
    throw "ER6 Defender trigger matrix found $($payload.scan_error_count) scan error(s)"
}
