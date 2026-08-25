[CmdletBinding()]
param(
    [switch]$NoWatch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$utf8Support = Join-Path $PSScriptRoot 'windows-host-tauri-utf8.ps1'
. $utf8Support
$watchSupport = Join-Path $PSScriptRoot 'windows-host-tauri-watch.ps1'
. $watchSupport
$utf8Scope = Enter-AngmooUtf8NativeCommandScope

try {

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$preflightScript = Join-Path $PSScriptRoot 'desktop-preflight.ps1'
$baseComposePath = Join-Path $repoRoot 'compose.yml'
$devComposePath = Join-Path $repoRoot 'compose.dev.yml'
$composeFiles = @('-f', $baseComposePath, '-f', $devComposePath)
$protectedDataRoot = Join-Path $env:LOCALAPPDATA 'Angmoo'
$protectedChildren = @('canonical', 'graph', 'media', 'secrets')
$watchProcess = $null

function Get-ProtectedDataFingerprint {
    param([Parameter(Mandatory = $true)][string]$Root)
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) { return 'absent' }
    $records = [System.Collections.Generic.List[string]]::new()
    foreach ($child in $protectedChildren) {
        $directory = Join-Path $Root $child
        if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
            $records.Add("$child|absent")
            continue
        }
        foreach ($file in Get-ChildItem -LiteralPath $directory -Recurse -File | Sort-Object FullName) {
            $relative = $file.FullName.Substring($Root.Length).TrimStart('\')
            $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            $records.Add("$relative|$($file.Length)|$hash")
        }
    }
    $bytes = [Text.Encoding]::UTF8.GetBytes(($records -join "`n"))
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }
}

function Get-ComposeRecords {
    return @(
        Invoke-AngmooNativeJsonCommand -CommandType 'compose-ps' -AllowEmpty -JsonLines -Command {
            & docker compose @composeFiles ps --format json 2>$null
        }
    )
}

function Assert-ComposeReady {
    $records = @(Get-ComposeRecords)
    foreach ($service in @('backend', 'frontend')) {
        $record = @($records | Where-Object { $_.Service -eq $service })
        if ($record.Count -ne 1 -or $record[0].State -ne 'running' -or $record[0].Health -ne 'healthy') {
            throw "docker_service_not_ready:$service"
        }
    }
    $diagnostics = @(
        Invoke-AngmooNativeJsonCommand -CommandType 'compose-backend-diagnostics' -Command {
            & docker compose @composeFiles exec -T backend /usr/local/bin/angmoo-backend-entrypoint contributor-diagnostics 2>$null
        }
    )[0]
    if (
        $diagnostics.runtime_profile -ne 'CONTRIBUTOR_EMBEDDED' -or
        $diagnostics.persistence_provider -ne 'sqlite' -or
        $diagnostics.graph_provider -ne 'ladybug'
    ) {
        throw 'docker_backend_runtime_contract_mismatch'
    }
    $health = @(
        Invoke-AngmooNativeJsonCommand -CommandType 'compose-backend-health' -Command {
            & docker compose @composeFiles exec -T backend python -c `
                "import json,urllib.request; print(json.dumps(json.load(urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5)), separators=(',', ':')))" 2>$null
        }
    )[0]
    if (
        $health.profile -ne 'CONTRIBUTOR_EMBEDDED' -or
        $health.persistence -ne 'sqlite' -or
        $health.graph -ne 'ladybug' -or
        $health.components.scheduler -notin @('ready', 'running') -or
        $health.components.projector -notin @('ready', 'running')
    ) {
        throw 'docker_backend_component_contract_mismatch'
    }
    $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:3000/' -TimeoutSec 10
    if ($response.StatusCode -ne 200) { throw 'docker_frontend_not_ready' }
}

function Assert-NoHostSidecar {
    if (@(Get-Process -Name 'angmoo-sidecar' -ErrorAction SilentlyContinue).Count -ne 0) {
        throw 'contributor_bridge_spawned_host_sidecar'
    }
}

$powershellExe = (Get-Command powershell.exe -ErrorAction Stop).Source
$preflightOutput = & $powershellExe -NoProfile -ExecutionPolicy Bypass -File $preflightScript -Json
$preflightExit = $LASTEXITCODE
if ($preflightExit -ne 0) {
    if ($preflightOutput) { Write-Host $preflightOutput }
    throw "windows_host_tauri_preflight_failed:$preflightExit"
}
$preflight = @(ConvertFrom-AngmooJsonText -Content (($preflightOutput -join "`n").Trim()) `
    -FailureCode 'preflight_json_decode_failed')[0]
if ($preflight.state -ne 'passed') { throw 'windows_host_tauri_preflight_blocked' }

$beforeFingerprint = Get-ProtectedDataFingerprint -Root $protectedDataRoot
$commit = (& git -C $repoRoot rev-parse HEAD).Trim()
$shortCommit = $commit.Substring(0, 12)
$previousEnvironment = @{
    ANGMOO_PORT = [Environment]::GetEnvironmentVariable('ANGMOO_PORT', 'Process')
    ANGMOO_VERSION = [Environment]::GetEnvironmentVariable('ANGMOO_VERSION', 'Process')
    ANGMOO_VCS_REF = [Environment]::GetEnvironmentVariable('ANGMOO_VCS_REF', 'Process')
}
$cleanupError = $null

try {
    $env:ANGMOO_PORT = '3000'
    $env:ANGMOO_VERSION = "0.4.0-dev-$shortCommit"
    $env:ANGMOO_VCS_REF = $commit
    Assert-NoHostSidecar

    Push-Location $repoRoot
    try {
        Write-Host 'Preparing the shared Docker CONTRIBUTOR_EMBEDDED stack...'
        & docker compose @composeFiles up -d --build --wait --wait-timeout 300
        if ($LASTEXITCODE -ne 0) { throw 'docker_contributor_stack_start_failed' }
        Assert-ComposeReady

        if (-not $NoWatch) {
            Write-Host 'Starting Docker Compose Watch; containers and the named volume remain after Tauri exits.'
            Clear-AngmooOwnedComposeWatchOrphans -BaseComposePath $baseComposePath `
                -DevComposePath $devComposePath
            $watchArguments = @(
                'compose', '--ansi', 'never',
                '-f', $baseComposePath, '-f', $devComposePath,
                'watch', '--no-up'
            )
            $watchProcess = Start-Process -FilePath (Get-Command docker).Source `
                -ArgumentList $watchArguments -WorkingDirectory $repoRoot -NoNewWindow -PassThru
            if ($watchProcess.WaitForExit(1500)) {
                $legacyPids = @(Get-AngmooLegacyUnscopedComposeWatchWorkers |
                    ForEach-Object { $_.ProcessId }) -join ','
                throw "docker_compose_watch_exited_early:exit=$($watchProcess.ExitCode) legacy_unscoped_pids=$legacyPids"
            }
            Wait-AngmooOwnedComposeWatchCount -ExpectedCount 1 -BaseComposePath $baseComposePath `
                -DevComposePath $devComposePath | Out-Null
        }

        Write-Host "Launching Angmoo Host Tauri dev for exact commit $commit"
        Write-Host 'The host shell will use Docker data only; the installed Angmoo data fingerprint is guarded.'
        & npm.cmd --prefix (Join-Path $repoRoot 'desktop') run dev:docker-bridge
        if ($LASTEXITCODE -ne 0) { throw "host_tauri_dev_failed:$LASTEXITCODE" }
    } finally {
        Pop-Location
    }
} finally {
    try {
        if (-not $NoWatch) {
            Stop-AngmooOwnedComposeWatch -LauncherProcess $watchProcess `
                -BaseComposePath $baseComposePath -DevComposePath $devComposePath
        }
    } catch {
        $cleanupError = $_.Exception.Message
    }
    try {
        Assert-NoHostSidecar
        $afterFingerprint = Get-ProtectedDataFingerprint -Root $protectedDataRoot
        if ($afterFingerprint -ne $beforeFingerprint) {
            $cleanupError = 'installed_product_data_changed_during_contributor_bridge'
        }
    } catch {
        if (-not $cleanupError) { $cleanupError = $_.Exception.Message }
    }
    foreach ($name in $previousEnvironment.Keys) {
        $value = $previousEnvironment[$name]
        if ($null -eq $value) {
            [Environment]::SetEnvironmentVariable($name, $null, 'Process')
        } else {
            [Environment]::SetEnvironmentVariable($name, $value, 'Process')
        }
    }
    if ($cleanupError) { throw $cleanupError }
}

Write-Host 'Angmoo Windows Host Tauri dev stopped cleanly.'
Write-Host 'Docker frontend/backend and angmoo_contributor_embedded_data were preserved.'
} finally {
    Exit-AngmooUtf8NativeCommandScope -State $utf8Scope
}
