param(
    [switch]$Bootstrap,
    [switch]$ProjectOnce,
    [string]$DatabaseUrl = $env:DATABASE_URL
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$composeFile = Join-Path $repoRoot 'compose.neo4j.yml'
. (Join-Path $PSScriptRoot 'neo4j-local-secret.ps1')

if ($ProjectOnce -and [string]::IsNullOrWhiteSpace($DatabaseUrl)) {
    throw 'database_url_required_for_project_once'
}
$previousDatabaseUrl = $env:DATABASE_URL
if (-not [string]::IsNullOrWhiteSpace($DatabaseUrl)) {
    $env:DATABASE_URL = $DatabaseUrl
}

Initialize-AngmooNeo4jLocalEnvironment
try {
    & docker compose -f $composeFile up -d neo4j | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'neo4j_compose_start_failed'
    }

    $deadline = [DateTimeOffset]::UtcNow.AddMinutes(3)
    do {
        $status = (& docker inspect --format '{{.State.Health.Status}}' angmoo-p7-neo4j 2>$null).Trim()
        if ($status -eq 'healthy') {
            break
        }
        Start-Sleep -Seconds 2
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    if ($status -ne 'healthy') {
        throw 'neo4j_health_timeout'
    }
    Write-Host 'neo4j_ready=true'

    if ($Bootstrap -or $ProjectOnce) {
        Push-Location (Join-Path $repoRoot 'backend')
        try {
            if ($ProjectOnce) {
                $arguments = @('run', 'python', 'scripts/run_graph_projection_worker.py', '--once')
            } else {
                $arguments = @('run', 'python', 'scripts/run_graph_projection_worker.py', '--bootstrap-only')
            }
            if ($Bootstrap -and $ProjectOnce) {
                $arguments += '--bootstrap'
            }
            & uv @arguments
            if ($LASTEXITCODE -ne 0) {
                throw 'graph_projector_once_failed'
            }
        } finally {
            Pop-Location
        }
    }
} finally {
    Clear-AngmooNeo4jLocalEnvironment
    if ($null -eq $previousDatabaseUrl) {
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    } else {
        $env:DATABASE_URL = $previousDatabaseUrl
    }
}
