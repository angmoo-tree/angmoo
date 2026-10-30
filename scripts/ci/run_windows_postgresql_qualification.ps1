[CmdletBinding()]
param(
  [Parameter(Mandatory)][string]$InstallerRoot,
  [Parameter(Mandatory)][ValidateSet('clean-install','upgrade-013','failure-recovery')][string]$Kind,
  [Parameter(Mandatory)][string]$Python,
  [Parameter(Mandatory)][string]$Output
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
if ($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted') {
  throw 'windows_pg_hosted_only'
}
$candidates = @(Get-ChildItem -LiteralPath $InstallerRoot -Recurse -File -Filter 'Angmoo_*_x64-setup.exe')
if ($candidates.Count -ne 1) { throw 'windows_pg_installer_not_unique' }
$installer = $candidates[0]
$digest = (Get-FileHash -LiteralPath $installer.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
$sums = @(Get-ChildItem -LiteralPath $InstallerRoot -Recurse -File -Filter SHA256SUMS)
if ($sums.Count -ne 1 -or (Get-Content -LiteralPath $sums[0].FullName -Raw).Trim() -cne "$digest  $($installer.Name)") {
  throw 'windows_pg_installer_checksums_mismatch'
}
$baseline = @(Get-MpThreatDetection -ErrorAction Stop | Select-Object -ExpandProperty DetectionID)
function Assert-NoNewDefenderDetection([string]$Stage) {
  if (@(Get-MpThreat -ErrorAction Stop | Where-Object IsActive).Count -gt 0) { throw "windows_pg_defender_active:$Stage" }
  if (@(Get-MpThreatDetection -ErrorAction Stop | Where-Object DetectionID -notin $baseline).Count -gt 0) {
    throw "windows_pg_defender_new_detection:$Stage"
  }
}
Start-MpScan -ScanType CustomScan -ScanPath $installer.FullName
Assert-NoNewDefenderDetection 'installer_preinstall_scan'
$work = Join-Path $env:RUNNER_TEMP "angmoo-pg-private-$Kind"
& $Python "$PSScriptRoot/run_windows_postgresql_qualification.py" `
  --installer $installer.FullName --installer-sha256 $digest --source-sha $env:SOURCE_SHA `
  --kind $Kind --work $work --output $Output
if ($LASTEXITCODE -ne 0) { throw 'windows_pg_qualification_failed' }
$app = Join-Path $env:LOCALAPPDATA 'Angmoo/app'
$verify = Join-Path $app 'verify-installed-payload.ps1'
& $verify -AppRoot $app
if ($LASTEXITCODE -ne 0) { throw 'windows_pg_installed_payload_mismatch' }
$before = @{}
Get-ChildItem -LiteralPath $app -Recurse -File | ForEach-Object {
  $before[$_.FullName] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
}
Start-MpScan -ScanType CustomScan -ScanPath $app
Assert-NoNewDefenderDetection 'installed_postrun_scan'
foreach ($file in $before.Keys) {
  if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $before[$file]) { throw 'windows_pg_payload_changed_during_scan' }
}
if ((Get-FileHash -LiteralPath $installer.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -cne $digest) {
  throw 'windows_pg_installer_changed'
}
@{status='PASS';kind=$Kind;stages=@('installer_preinstall_scan','installed_postrun_scan');interactive_full_delete='user_gate_required'} |
  ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $env:RUNNER_TEMP "angmoo-windows-defender-evidence-$Kind.json") -Encoding utf8
