Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$localScripts = Get-ChildItem -LiteralPath (Join-Path $repoRoot 'scripts\local') -Filter '*.ps1' -File
if (-not $localScripts) {
    throw 'windows_local_scripts_missing'
}

foreach ($script in $localScripts) {
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $script.FullName,
        [ref]$tokens,
        [ref]$errors
    )
    if ($errors.Count -gt 0) {
        throw "powershell_parse_failed:$($script.Name)"
    }
}

foreach ($launcherFile in @(
    (Join-Path $repoRoot 'angmoo.ps1'),
    (Join-Path $repoRoot 'launcher\windows\Angmoo.Launcher.psm1')
)) {
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $launcherFile,
        [ref]$tokens,
        [ref]$errors
    )
    if ($errors.Count -gt 0) {
        throw "powershell_parse_failed:$launcherFile"
    }
}

$launcher = Join-Path $repoRoot 'angmoo.ps1'
$helpPayload = & $launcher help --json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $helpPayload.schema_version -ne 'angmoo-launcher-result-v1') {
    throw 'launcher_help_contract_failed'
}

$blockedPayload = & $launcher stop --volumes --json | ConvertFrom-Json
if ($LASTEXITCODE -ne 40 -or $blockedPayload.error_code -ne 'destructive_command_blocked') {
    throw 'launcher_destructive_option_was_not_blocked'
}

$fakeRoot = Join-Path ([IO.Path]::GetTempPath()) "angmoo-launcher-$([Guid]::NewGuid().ToString('N'))"
$fakeLog = Join-Path $fakeRoot 'docker-arguments.log'
New-Item -ItemType Directory -Path $fakeRoot | Out-Null
$fakeDocker = @'
@echo off
echo %*>>"%ANGMOO_FAKE_DOCKER_LOG%"
if "%1"=="info" echo 29.6.1& exit /b 0
if "%1"=="image" exit /b 0
if "%1"=="volume" exit /b 0
if "%1"=="system" echo {"Type":"Images","TotalCount":"2","Active":"2","Size":"1.4GB","Reclaimable":"0B"}& exit /b 0
if "%1"=="stats" echo {"Name":"synthetic-backend","CPUPerc":"0.10%%","MemUsage":"10MiB / 1GiB"}& exit /b 0
if "%1"=="inspect" echo {"Name":"/synthetic-backend","RestartCount":0,"Image":"sha256:1234567890abcdef1234567890abcdef"}& exit /b 0
echo %* | findstr /C:"compose version --short" >nul && (echo 5.3.1& exit /b 0)
echo %* | findstr /C:" config --quiet" >nul && exit /b 0
echo %* | findstr /C:" port frontend 3000" >nul && (
  if "%ANGMOO_FAKE_RUNNING%"=="1" (echo 127.0.0.1:45999& exit /b 0) else (exit /b 1)
)
echo %* | findstr /C:" ps --all --format json" >nul && (
  if "%ANGMOO_FAKE_RUNNING%"=="1" (
    echo [{"Service":"backend","Name":"synthetic-backend","State":"running","Health":"healthy","Image":"synthetic"},{"Service":"frontend","Name":"synthetic-frontend","State":"running","Health":"healthy","Image":"synthetic"},{"Service":"neo4j","Name":"synthetic-neo4j","State":"running","Health":"healthy","Image":"synthetic"},{"Service":"postgresql","Name":"synthetic-postgresql","State":"running","Health":"healthy","Image":"synthetic"},{"Service":"projector","Name":"synthetic-projector","State":"running","Health":"healthy","Image":"synthetic"},{"Service":"scheduler","Name":"synthetic-scheduler","State":"running","Health":"healthy","Image":"synthetic"}]
  ) else (
    echo []
  )
  exit /b 0
)
echo %* | findstr /C:" exec -T backend /usr/local/bin/angmoo-backend-entrypoint diagnostics" >nul && (
  echo {"schema_version":"local-runtime-status-v1","installation_state":"ready","version":"0.3.0","components":[],"migration":{"state":"ready","current_revision":"20260816_0080","head_revision":"20260816_0080"},"scheduler":{"state":"running","fencing_epoch":7},"projector":{"state":"ready","pending_count":0,"retry_count":0,"failed_count":0,"dead_letter_count":0},"provider_usage":{"recent_call_count":0,"kill_switch_enabled":false},"owner":{"bootstrap_state":"claimed","registered_world_count":1,"active_world_count":1,"active_world_character_count":1},"activity":{},"capabilities":{}}
  exit /b 0
)
echo %* | findstr /C:" stop --timeout 60" >nul && exit /b 0
echo %* | findstr /C:" up -d" >nul && exit /b 0
echo %* | findstr /C:" logs --tail" >nul && (set "google_prefix=A"& echo synthetic log APP_SECRET=%google_prefix%IzaZZZZZZZZZZZZZZZZZZZZZZZZ& exit /b 0)
exit /b 0
'@
Set-Content -LiteralPath (Join-Path $fakeRoot 'docker.cmd') -Value $fakeDocker -Encoding ascii

$previousPath = $env:PATH
$previousFakeLog = $env:ANGMOO_FAKE_DOCKER_LOG
$previousFakeRunning = $env:ANGMOO_FAKE_RUNNING
try {
    $env:PATH = "$fakeRoot;$previousPath"
    $env:ANGMOO_FAKE_DOCKER_LOG = $fakeLog
    $env:ANGMOO_FAKE_RUNNING = '0'
    Push-Location $fakeRoot
    try {
        $statusPayload = & $launcher status --json --project-name synthetic-l2 --port 45999 | ConvertFrom-Json
        $statusJsonExit = $LASTEXITCODE
        $statusHuman = @(& $launcher status --project-name synthetic-l2 --port 45999)
        $statusHumanExit = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($statusJsonExit -ne 0 -or $statusHumanExit -ne 0 -or $statusPayload.state -ne 'stopped') {
        throw 'launcher_fake_status_failed'
    }
    if (-not ($statusHuman -join "`n").Contains('Angmoo state: stopped.')) {
        throw 'launcher_human_json_parity_failed'
    }

    $env:ANGMOO_FAKE_RUNNING = '1'
    $startPayload = & $launcher start --json --project-name synthetic-l2 --port 45999 | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or -not $startPayload.details.idempotent_no_op) {
        throw 'launcher_fake_repeated_start_was_not_idempotent'
    }
    $doctorPayload = & $launcher doctor --json --project-name synthetic-l2 --port 45999 | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $doctorPayload.state -ne 'ready') {
        throw 'launcher_aggregate_doctor_failed'
    }
    if ($doctorPayload.details.application.payload.schema_version -ne 'local-runtime-status-v1') {
        throw 'launcher_application_status_missing'
    }
    if ($doctorPayload.details.host.docker_storage.state -ne 'ready') {
        throw 'launcher_host_storage_status_missing'
    }
    if (@($doctorPayload.details.host.container_resources).Count -ne 6) {
        throw 'launcher_container_resource_status_missing'
    }
    $doctorSerialized = $doctorPayload | ConvertTo-Json -Depth 20 -Compress
    if ($doctorSerialized -match 'AIzaZZZZ' -or $doctorSerialized -match 'APP_SECRET=AIza') {
        throw 'launcher_doctor_secret_canary_leaked'
    }
    $logsPayload = & $launcher logs --json --project-name synthetic-l2 --port 45999 | ConvertFrom-Json
    $logsSerialized = $logsPayload | ConvertTo-Json -Depth 20 -Compress
    if ($logsSerialized -match 'AIzaZZZZ' -or $logsSerialized -match 'APP_SECRET=AIza') {
        throw 'launcher_logs_secret_canary_leaked'
    }
    $stopPayload = & $launcher stop --json --project-name synthetic-l2 --port 45999 | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or -not $stopPayload.details.volumes_preserved) {
        throw 'launcher_fake_stop_failed'
    }
    $dockerArguments = Get-Content -LiteralPath $fakeLog -Raw
    if (-not $dockerArguments.Contains('stop --timeout 60')) {
        throw 'launcher_stop_did_not_use_compose_stop'
    }
    if ($dockerArguments.Contains('--volumes') -or $dockerArguments.Contains(' -v')) {
        throw 'launcher_stop_requested_volume_deletion'
    }

    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 45997)
    try {
        $listener.Start()
        $conflictPayload = & $launcher doctor --json --project-name synthetic-conflict --port 45997 | ConvertFrom-Json
        if ($LASTEXITCODE -ne 11 -or $conflictPayload.error_code -ne 'host_port_conflict') {
            throw 'launcher_port_conflict_was_not_normalized'
        }
    } finally {
        $listener.Stop()
    }

    $lockProject = 'synthetic-lock'
    $lockIdentity = "$($repoRoot.ToLowerInvariant())|$lockProject"
    $lockSha = [Security.Cryptography.SHA256]::Create()
    try {
        $lockDigest = $lockSha.ComputeHash([Text.Encoding]::UTF8.GetBytes($lockIdentity))
    } finally {
        $lockSha.Dispose()
    }
    $lockHex = -join ($lockDigest | ForEach-Object { $_.ToString('x2') })
    $lockName = "Local\AngmooLauncher-$lockHex"
    $lockReady = Join-Path $fakeRoot 'lock-ready'
    $lockHelper = Join-Path $fakeRoot 'hold-lock.ps1'
    Set-Content -LiteralPath $lockHelper -Encoding ascii -Value @'
param([string]$Name, [string]$ReadyPath)
$mutex = [Threading.Mutex]::new($false, $Name)
$owns = $mutex.WaitOne(0)
try {
    if (-not $owns) { exit 2 }
    Set-Content -LiteralPath $ReadyPath -Value ready -Encoding ascii
    Start-Sleep -Seconds 30
} finally {
    if ($owns) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
'@
    $lockProcess = Start-Process powershell -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $lockHelper,
        '-Name', $lockName, '-ReadyPath', $lockReady
    ) -WindowStyle Hidden -PassThru
    try {
        for ($attempt = 0; $attempt -lt 50 -and -not (Test-Path $lockReady); $attempt++) {
            Start-Sleep -Milliseconds 100
        }
        if (-not (Test-Path $lockReady)) { throw 'launcher_lock_fixture_failed' }
        $lockPayload = & $launcher start --json --project-name $lockProject --port 45998 | ConvertFrom-Json
        if ($LASTEXITCODE -ne 21 -or $lockPayload.error_code -ne 'lifecycle_lock_held') {
            throw 'launcher_concurrent_lifecycle_was_not_blocked'
        }
    } finally {
        if (-not $lockProcess.HasExited) { Stop-Process -Id $lockProcess.Id -Force }
    }

    $emptyPath = Join-Path $fakeRoot 'empty-path'
    New-Item -ItemType Directory -Path $emptyPath | Out-Null
    $env:PATH = $emptyPath
    $unavailablePayload = & $launcher status --json --project-name synthetic-unavailable | ConvertFrom-Json
    if ($LASTEXITCODE -ne 10 -or $unavailablePayload.error_code -ne 'docker_engine_unavailable') {
        throw 'launcher_docker_unavailable_was_not_normalized'
    }
} finally {
    $env:PATH = $previousPath
    $env:ANGMOO_FAKE_DOCKER_LOG = $previousFakeLog
    $env:ANGMOO_FAKE_RUNNING = $previousFakeRunning
    Remove-Item -LiteralPath $fakeRoot -Recurse -Force -ErrorAction SilentlyContinue
}

$secretScript = Get-Content -LiteralPath (Join-Path $repoRoot 'scripts\local\neo4j-local-secret.ps1') -Raw -Encoding utf8
foreach ($marker in @(
    'Set-AngmooCurrentUserOnlyAcl',
    'ConvertFrom-SecureString',
    'ConvertFrom-AngmooSecureStringInMemory',
    'Clear-AngmooNeo4jLocalEnvironment'
)) {
    if (-not $secretScript.Contains($marker)) {
        throw "neo4j_secret_contract_missing:$marker"
    }
}

$plain = "synthetic-dpapi-$([Guid]::NewGuid().ToString('N'))"
try {
    $secure = ConvertTo-SecureString -String $plain -AsPlainText -Force
    $ciphertext = ConvertFrom-SecureString -SecureString $secure
    $roundTripSecure = ConvertTo-SecureString -String $ciphertext
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($roundTripSecure)
    try {
        $roundTrip = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
    if ($roundTrip -ne $plain) {
        throw 'dpapi_round_trip_mismatch'
    }
} finally {
    $plain = $null
    $roundTrip = $null
    $secure = $null
    $roundTripSecure = $null
    $ciphertext = $null
}

Write-Host "windows_local_smoke=pass scripts=$($localScripts.Count) launcher=pass dpapi=pass"
exit 0
