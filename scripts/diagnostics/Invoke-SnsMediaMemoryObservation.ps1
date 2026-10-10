param(
    [Parameter(Mandatory)][string]$DataRoot,
    [Parameter(Mandatory)][string]$SessionId,
    [Parameter(Mandatory)][string]$OutputRoot,
    [string]$DockerContainer,
    [string]$PythonExe,
    [switch]$ReadOnlySmoke,
    [ValidateRange(60,3600)][int]$IntervalSeconds = 60,
    [ValidateRange(0,300)][int]$MaxFlushSeconds = 300
)
$ErrorActionPreference = 'Stop'
if (-not (Get-Command ConvertFrom-Json).Parameters.ContainsKey('DateKind')) { throw 'collector_requires_powershell_datekind_string' }
if ($SessionId -notmatch '^sns-[0-9a-f]{32}$') { throw 'collector_session_invalid' }
$taskRepository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
Import-Module (Join-Path $PSScriptRoot 'SnsCollectorPolicy.psm1') -Force
if (-not $PythonExe) { $PythonExe = if ($DockerContainer) { '/workspace/backend/.venv/bin/python' } else { Join-Path $taskRepository 'backend/.venv/Scripts/python.exe' } }
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$taskOutput = (Get-Item -LiteralPath $OutputRoot).FullName
$probeSource = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'sns_media_memory_probe.py') -Raw -Encoding UTF8
$officialScript = if ($DockerContainer) { '/workspace/backend/scripts/sns_observation.py' } else { Join-Path $taskRepository 'backend/scripts/sns_observation.py' }
function Read-JsonString([string]$Value) { return Read-CollectorJson $Value }
function Get-UtcInstant($Value) { return Get-CollectorUtcInstant $Value }
function Invoke-Official([string[]]$Arguments) {
    $callArgs = @($officialScript, '--data-root', $DataRoot) + $Arguments
    $lines = if ($DockerContainer) { & docker exec $DockerContainer $PythonExe @callArgs } else { & $PythonExe @callArgs }
    if ($LASTEXITCODE -ne 0) { throw 'collector_official_command_failed' }
    return Read-JsonString ($lines -join "`n")
}
function Invoke-Probe {
    $callArgs = @('--data-root', $DataRoot, '--session', $SessionId)
    $lines = if ($DockerContainer) { $probeSource | & docker exec -i $DockerContainer $PythonExe - @callArgs } else { & $PythonExe (Join-Path $PSScriptRoot 'sns_media_memory_probe.py') @callArgs }
    if ($LASTEXITCODE -ne 0) { throw 'collector_probe_failed' }
    return Read-JsonString ($lines -join "`n")
}
$health = [ordered]@{ schema='sns-media-memory-collector.v1'; session_id=$SessionId; state='COLLECTING'; source_revision='unknown'; planned_snapshots=0; successful_snapshots=0; failed_snapshots=0; missing_snapshots=0; last_probe_success=$null; last_status_success=$null; last_flush_success=$null; last_export_success=$null; last_copy_success=$null; probe_error=$null; degraded=$false; flush_complete=$false; export_success=$false; copy_success=$false }
function Save-Health { $health | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $taskOutput 'collector-health.json') -Encoding UTF8 }
$failures = 0
if ($ReadOnlySmoke) {
    try { $snapshot=Invoke-Probe; $snapshot | ConvertTo-Json -Depth 14 | Set-Content -LiteralPath (Join-Path $taskOutput 'smoke.json') -Encoding UTF8; $health.state='SMOKE_COMPLETE'; $health.successful_snapshots=1; $health.planned_snapshots=1; $health.last_probe_success=[DateTimeOffset]::UtcNow.ToString('o') }
    catch { $health.state='ERROR'; $health.probe_error='collector_probe_failed'; $health.failed_snapshots=1 }
    Save-Health
    if ($health.state -eq 'ERROR') { exit 2 }; exit 0
}
# Inspect only an existing authorized session. This script never starts it.
$status = Invoke-Official @('status','--session',$SessionId)
$health.last_status_success=[DateTimeOffset]::UtcNow.ToString('o')
$manifest = if ($DockerContainer) {
    $lines = & docker exec $DockerContainer cat "$DataRoot/diagnostics/sns/$SessionId/manifest.json"
    if ($LASTEXITCODE -ne 0) { throw 'collector_manifest_failed' }; Read-JsonString ($lines -join "`n")
} else { Read-JsonString (Get-Content -LiteralPath (Join-Path $DataRoot "diagnostics/sns/$SessionId/manifest.json") -Raw -Encoding UTF8) }
$end = Get-UtcInstant $manifest.ends_at
$tail = Get-UtcInstant $manifest.tail_ends_at
$health.source_revision=$manifest.source_revision
$health.ends_utc=$end.ToString('o'); $health.tail_ends_utc=$tail.ToString('o')
while ([DateTimeOffset]::UtcNow -lt $tail) {
    $health.planned_snapshots++
    if (-not $health.degraded) {
        try {
            $snapshot=Invoke-Probe
            $snapshot | ConvertTo-Json -Depth 14 | Set-Content -LiteralPath (Join-Path $taskOutput ('snapshot-{0:D5}.json' -f $health.planned_snapshots)) -Encoding UTF8
            $failures=Update-CollectorProbeHealth $health $true $failures
        } catch { $failures=Update-CollectorProbeHealth $health $false $failures }
    } else { $health.missing_snapshots++ }
    try { $status=Invoke-Official @('status','--session',$SessionId); $status | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $taskOutput 'official-status.json') -Encoding UTF8; $health.last_status_success=[DateTimeOffset]::UtcNow.ToString('o') }
    catch { $health.status_error='collector_status_failed' }
    Save-Health
    $remaining=[Math]::Ceiling(($tail-[DateTimeOffset]::UtcNow).TotalSeconds)
    if ($remaining -gt 0) { Start-Sleep -Seconds ([Math]::Min($IntervalSeconds,$remaining)) }
}
$health.state='FINALIZING'; Save-Health
try { $snapshot=Invoke-Probe; $snapshot | ConvertTo-Json -Depth 14 | Set-Content -LiteralPath (Join-Path $taskOutput 'final-snapshot.json') -Encoding UTF8; $health.last_probe_success=[DateTimeOffset]::UtcNow.ToString('o'); $health.final_probe_success=$true }
catch { $health.final_probe_error='collector_probe_failed' }
$flushDeadline=[DateTimeOffset]::UtcNow.AddSeconds($MaxFlushSeconds)
do {
    try {
        $status=Invoke-Official @('status','--session',$SessionId)
        $health.last_status_success=[DateTimeOffset]::UtcNow.ToString('o')
        $recorders=@($status.recorder_health)
        $health.flush_complete=$recorders.Count -gt 0 -and @($recorders | Where-Object { $_.flush_complete -ne $true }).Count -eq 0
        if ($health.flush_complete) { $health.last_flush_success=[DateTimeOffset]::UtcNow.ToString('o') }
    } catch { $health.status_error='collector_status_failed' }
    if ($health.flush_complete -or [DateTimeOffset]::UtcNow -ge $flushDeadline) { break }
    $remainingFlushMs=[Math]::Max(0,($flushDeadline-[DateTimeOffset]::UtcNow).TotalMilliseconds)
    Start-Sleep -Milliseconds ([int][Math]::Floor([Math]::Min(30000,$remainingFlushMs)))
} while ([DateTimeOffset]::UtcNow -lt $flushDeadline)
try {
    $destination=if ($DockerContainer) { "$DataRoot/diagnostics/export-$SessionId-$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())" } else { Join-Path $taskOutput 'export' }
    $result=Invoke-Official @('export','--session',$SessionId,'--output',$destination)
    $health.export_success=$true
    $health.last_export_success=[DateTimeOffset]::UtcNow.ToString('o')
    if ($DockerContainer) { & docker cp "${DockerContainer}:$destination" (Join-Path $taskOutput 'export'); if ($LASTEXITCODE -ne 0) { throw 'collector_copy_failed' } }
    $health.copy_success=$true
    $health.last_copy_success=[DateTimeOffset]::UtcNow.ToString('o')
    $evidencePath=Join-Path $taskOutput 'export/situation-evidence-coverage.json'
    $health.auxiliary_status=if ([IO.File]::Exists($evidencePath)) {
        $aux=Read-JsonString (Get-Content -LiteralPath $evidencePath -Raw -Encoding UTF8)
        if ($aux.situation_evidence_complete -eq $true) { 'COMPLETE' } elseif ($aux.support -eq 'unsupported') { 'UNSUPPORTED' } else { 'UNKNOWN' }
    } else { 'UNKNOWN' }
} catch { $health.export_error='collector_export_or_copy_failed' }
$health.state=Get-CollectorFinalState $health
Save-Health
if ($health.state -eq 'ERROR') { exit 2 }
