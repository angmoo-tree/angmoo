function Read-CollectorJson([string]$Value) {
    if (-not (Get-Command ConvertFrom-Json).Parameters.ContainsKey('DateKind')) { throw 'collector_requires_powershell_datekind_string' }
    return $Value | ConvertFrom-Json -DateKind String
}
function Get-CollectorUtcInstant($Value) {
    if ($Value -isnot [string] -or $Value -notmatch '(Z|[+-]\d{2}:\d{2})$') { throw 'collector_time_offset_string_required' }
    return [DateTimeOffset]::Parse($Value, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::None).ToUniversalTime()
}
function Update-CollectorProbeHealth($Health, [bool]$Success, [int]$Failures) {
    if ($Success) { $Health.successful_snapshots++; $Health.last_probe_success=[DateTimeOffset]::UtcNow.ToString('o'); return 0 }
    $Health.failed_snapshots++; $Health.probe_error='collector_probe_failed'
    $Failures++
    if ($Failures -ge 3) { $Health.degraded=$true }
    return $Failures
}
function Get-CollectorFinalState($Health) {
    if (-not $Health.export_success -or -not $Health.copy_success) { return 'ERROR' }
    if ($Health.failed_snapshots -or $Health.final_probe_error -or -not $Health.flush_complete -or $Health.auxiliary_status -eq 'UNKNOWN') { return 'PARTIAL' }
    return 'EXPORTED_PENDING_REVIEW'
}
Export-ModuleMember -Function Read-CollectorJson,Get-CollectorUtcInstant,Update-CollectorProbeHealth,Get-CollectorFinalState
