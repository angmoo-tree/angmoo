[CmdletBinding()]
param(
    [switch]$NoWatch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$preflightScript = Join-Path $PSScriptRoot 'desktop-preflight.ps1'
$composeFiles = @('-f', 'compose.yml', '-f', 'compose.dev.yml')
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
    $lines = @(& docker compose @composeFiles ps --format json 2>$null)
    $content = ($lines -join "`n").Trim()
    if (-not $content) { return @() }
    if ($content.StartsWith('[')) { return @($content | ConvertFrom-Json) }
    return @($lines | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json })
}

function Assert-ComposeReady {
    $records = @(Get-ComposeRecords)
    foreach ($service in @('backend', 'frontend')) {
        $record = @($records | Where-Object { $_.Service -eq $service })
        if ($record.Count -ne 1 -or $record[0].State -ne 'running' -or $record[0].Health -ne 'healthy') {
            throw "docker_service_not_ready:$service"
        }
    }
    $diagnosticsRaw = & docker compose @composeFiles exec -T backend /usr/local/bin/angmoo-backend-entrypoint contributor-diagnostics
    if ($LASTEXITCODE -ne 0) { throw 'docker_backend_diagnostics_failed' }
    $diagnostics = $diagnosticsRaw | ConvertFrom-Json
    if (
        $diagnostics.runtime_profile -ne 'CONTRIBUTOR_EMBEDDED' -or
        $diagnostics.persistence_provider -ne 'sqlite' -or
        $diagnostics.graph_provider -ne 'ladybug'
    ) {
        throw 'docker_backend_runtime_contract_mismatch'
    }
    $healthRaw = & docker compose @composeFiles exec -T backend python -c `
        "import json,urllib.request; print(json.dumps(json.load(urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5)), separators=(',', ':')))"
    if ($LASTEXITCODE -ne 0) { throw 'docker_backend_health_failed' }
    $health = $healthRaw | ConvertFrom-Json
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
$preflight = $preflightOutput | ConvertFrom-Json
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
            $watchArguments = @(
                'compose', '--ansi', 'never',
                '-f', 'compose.yml', '-f', 'compose.dev.yml',
                'watch', '--no-up'
            )
            $watchProcess = Start-Process -FilePath (Get-Command docker).Source `
                -ArgumentList $watchArguments -WorkingDirectory $repoRoot -NoNewWindow -PassThru
        }

        Write-Host "Launching Angmoo Host Tauri dev for exact commit $commit"
        Write-Host 'The host shell will use Docker data only; the installed Angmoo data fingerprint is guarded.'
        & npm.cmd --prefix (Join-Path $repoRoot 'desktop') run dev:docker-bridge
        if ($LASTEXITCODE -ne 0) { throw "host_tauri_dev_failed:$LASTEXITCODE" }
    } finally {
        Pop-Location
    }
} finally {
    if ($watchProcess -and -not $watchProcess.HasExited) {
        Stop-Process -Id $watchProcess.Id -Force -ErrorAction SilentlyContinue
        $watchProcess.WaitForExit(5000) | Out-Null
    }
    try {
        Assert-NoHostSidecar
        $afterFingerprint = Get-ProtectedDataFingerprint -Root $protectedDataRoot
        if ($afterFingerprint -ne $beforeFingerprint) {
            $cleanupError = 'installed_product_data_changed_during_contributor_bridge'
        }
    } catch {
        $cleanupError = $_.Exception.Message
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
