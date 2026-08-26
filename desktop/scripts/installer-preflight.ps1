[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$AppRoot,
    [int]$TimeoutSeconds = 20
)

$ErrorActionPreference = 'Stop'
$expected = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Angmoo\app')).TrimEnd('\')
$actual = [System.IO.Path]::GetFullPath($AppRoot).TrimEnd('\')
if (-not [string]::Equals($actual, $expected, [System.StringComparison]::OrdinalIgnoreCase)) {
    Write-Error 'installer_app_root_invalid'
    exit 21
}

$appPrefix = $actual + '\'
function Get-InstalledRuntimeProcesses {
    @(
        Get-Process -Name 'angmoo-desktop', 'angmoo-sidecar' -ErrorAction SilentlyContinue |
            Where-Object {
                try {
                    $path = [System.IO.Path]::GetFullPath($_.Path)
                    $path.StartsWith($appPrefix, [System.StringComparison]::OrdinalIgnoreCase)
                }
                catch {
                    $false
                }
            }
    )
}

$hosts = @(Get-InstalledRuntimeProcesses | Where-Object { $_.ProcessName -eq 'angmoo-desktop' })
foreach ($hostProcess in $hosts) {
    try { [void]$hostProcess.CloseMainWindow() } catch { }
}

$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
do {
    $remaining = @(Get-InstalledRuntimeProcesses)
    if ($remaining.Count -eq 0) {
        Write-Output 'installer_runtime_processes_stopped'
        exit 0
    }
    Start-Sleep -Milliseconds 250
} while ([DateTime]::UtcNow -lt $deadline)

Write-Error 'installer_runtime_processes_still_running'
exit 23
