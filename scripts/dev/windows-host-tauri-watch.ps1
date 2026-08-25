Set-StrictMode -Version Latest

function Test-AngmooOwnedComposeWatchCommandLine {
    param(
        [AllowNull()][string]$CommandLine,
        [Parameter(Mandatory = $true)][string]$BaseComposePath,
        [Parameter(Mandatory = $true)][string]$DevComposePath
    )
    if ([string]::IsNullOrWhiteSpace($CommandLine)) { return $false }
    $basePath = [IO.Path]::GetFullPath($BaseComposePath)
    $devPath = [IO.Path]::GetFullPath($DevComposePath)
    return (
        $CommandLine.IndexOf($basePath, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $CommandLine.IndexOf($devPath, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $CommandLine -match '(?i)(^|\s)watch(?=\s|$)'
    )
}

function Get-AngmooOwnedComposeWatchWorkers {
    param(
        [Parameter(Mandatory = $true)][string]$BaseComposePath,
        [Parameter(Mandatory = $true)][string]$DevComposePath
    )
    $workers = @(
        Get-CimInstance Win32_Process -Filter "Name = 'docker-compose.exe'" -ErrorAction Stop |
            Where-Object {
                Test-AngmooOwnedComposeWatchCommandLine -CommandLine $_.CommandLine `
                    -BaseComposePath $BaseComposePath -DevComposePath $DevComposePath
            }
    )
    return $workers
}

function Get-AngmooLegacyUnscopedComposeWatchWorkers {
    return @(
        Get-CimInstance Win32_Process -Filter "Name = 'docker-compose.exe'" -ErrorAction Stop |
            Where-Object {
                $_.CommandLine -match '(?i)(^|\s)watch(?=\s|$)' -and
                $_.CommandLine -match '(?i)(^|\s)-f\s+"?compose\.yml"?(?=\s|$)' -and
                $_.CommandLine -match '(?i)(^|\s)-f\s+"?compose\.dev\.yml"?(?=\s|$)'
            }
    )
}

function Wait-AngmooOwnedComposeWatchCount {
    param(
        [Parameter(Mandatory = $true)][int]$ExpectedCount,
        [Parameter(Mandatory = $true)][string]$BaseComposePath,
        [Parameter(Mandatory = $true)][string]$DevComposePath,
        [int]$TimeoutSeconds = 10
    )
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $workers = @(Get-AngmooOwnedComposeWatchWorkers `
            -BaseComposePath $BaseComposePath -DevComposePath $DevComposePath)
        if ($workers.Count -eq $ExpectedCount) { return $workers }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)
    $pids = @($workers | ForEach-Object { $_.ProcessId }) -join ','
    throw "repo_compose_watch_count_mismatch:expected=$ExpectedCount actual=$($workers.Count) pids=$pids"
}

function Stop-AngmooProcessTree {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [int]$TimeoutSeconds = 10
    )
    if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { return }
    $taskkill = Join-Path $env:SystemRoot 'System32\taskkill.exe'
    & $taskkill /PID $ProcessId /T /F 1>$null 2>$null
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { return }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "process_tree_cleanup_failed:pid=$ProcessId"
}

function Clear-AngmooOwnedComposeWatchOrphans {
    param(
        [Parameter(Mandatory = $true)][string]$BaseComposePath,
        [Parameter(Mandatory = $true)][string]$DevComposePath
    )
    $active = [System.Collections.Generic.List[int]]::new()
    foreach ($worker in @(Get-AngmooOwnedComposeWatchWorkers `
        -BaseComposePath $BaseComposePath -DevComposePath $DevComposePath)) {
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId = $($worker.ParentProcessId)" `
            -ErrorAction SilentlyContinue
        $parentOwnsWatch = $null -ne $parent -and $parent.Name -eq 'docker.exe' -and `
            (Test-AngmooOwnedComposeWatchCommandLine -CommandLine $parent.CommandLine `
                -BaseComposePath $BaseComposePath -DevComposePath $DevComposePath)
        if ($parentOwnsWatch) {
            $active.Add([int]$worker.ProcessId)
        } else {
            Stop-AngmooProcessTree -ProcessId ([int]$worker.ProcessId)
        }
    }
    if ($active.Count -ne 0) {
        throw "repo_compose_watch_already_running:pids=$($active -join ',')"
    }
    Wait-AngmooOwnedComposeWatchCount -ExpectedCount 0 -BaseComposePath $BaseComposePath `
        -DevComposePath $DevComposePath | Out-Null
}

function Stop-AngmooOwnedComposeWatch {
    param(
        [AllowNull()][System.Diagnostics.Process]$LauncherProcess,
        [Parameter(Mandatory = $true)][string]$BaseComposePath,
        [Parameter(Mandatory = $true)][string]$DevComposePath
    )
    if ($null -ne $LauncherProcess -and -not $LauncherProcess.HasExited) {
        Stop-AngmooProcessTree -ProcessId $LauncherProcess.Id
    }
    foreach ($worker in @(Get-AngmooOwnedComposeWatchWorkers `
        -BaseComposePath $BaseComposePath -DevComposePath $DevComposePath)) {
        Stop-AngmooProcessTree -ProcessId ([int]$worker.ProcessId)
    }
    Wait-AngmooOwnedComposeWatchCount -ExpectedCount 0 -BaseComposePath $BaseComposePath `
        -DevComposePath $DevComposePath | Out-Null
}
