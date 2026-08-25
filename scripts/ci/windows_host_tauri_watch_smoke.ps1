Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$watchSupport = Join-Path $repoRoot 'scripts\dev\windows-host-tauri-watch.ps1'
. $watchSupport

$fixtureBase = 'C:\fixture\angmoo\compose.yml'
$fixtureDev = 'C:\fixture\angmoo\compose.dev.yml'
$owned = 'docker-compose.exe compose --ansi never -f C:\fixture\angmoo\compose.yml -f C:\fixture\angmoo\compose.dev.yml watch --no-up'
$otherRepo = 'docker-compose.exe compose --ansi never -f C:\fixture\other\compose.yml -f C:\fixture\other\compose.dev.yml watch --no-up'
$relativeLegacy = 'docker-compose.exe compose --ansi never -f compose.yml -f compose.dev.yml watch --no-up'
$notWatch = 'docker-compose.exe compose --ansi never -f C:\fixture\angmoo\compose.yml -f C:\fixture\angmoo\compose.dev.yml up --wait'

if (-not (Test-AngmooOwnedComposeWatchCommandLine -CommandLine $owned `
    -BaseComposePath $fixtureBase -DevComposePath $fixtureDev)) {
    throw 'owned_compose_watch_not_detected'
}
foreach ($commandLine in @($otherRepo, $relativeLegacy, $notWatch, $null)) {
    if (Test-AngmooOwnedComposeWatchCommandLine -CommandLine $commandLine `
        -BaseComposePath $fixtureBase -DevComposePath $fixtureDev) {
        throw "foreign_or_non_watch_process_claimed:$commandLine"
    }
}

$parent = $null
$child = $null
try {
    $childCommand = '$child = Start-Process -FilePath powershell.exe -ArgumentList @(''-NoProfile'',''-Command'',''Start-Sleep -Seconds 120'') -WindowStyle Hidden -PassThru; Wait-Process -Id $child.Id'
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($childCommand))
    $parent = Start-Process -FilePath powershell.exe `
        -ArgumentList @('-NoProfile', '-EncodedCommand', $encoded) -WindowStyle Hidden -PassThru
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        $child = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($parent.Id)" `
            -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq 'powershell.exe' } |
            Select-Object -First 1
        if ($null -ne $child) { break }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)
    if ($null -eq $child) { throw 'process_tree_fixture_child_missing' }

    Stop-AngmooProcessTree -ProcessId $parent.Id
    if (Get-Process -Id $parent.Id -ErrorAction SilentlyContinue) {
        throw 'process_tree_parent_survived'
    }
    if (Get-Process -Id $child.ProcessId -ErrorAction SilentlyContinue) {
        throw 'process_tree_child_survived'
    }
} finally {
    if ($null -ne $parent) {
        try { Stop-AngmooProcessTree -ProcessId $parent.Id } catch { }
    }
    if ($null -ne $child) {
        try { Stop-AngmooProcessTree -ProcessId $child.ProcessId } catch { }
    }
}

Write-Host 'windows-host-tauri-watch-smoke: PASS'
exit 0
