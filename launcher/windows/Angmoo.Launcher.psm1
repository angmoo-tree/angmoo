Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:LauncherRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script:ContractPath = Join-Path $script:LauncherRoot 'launcher\contract\local-launcher-v1.json'
$script:Contract = Get-Content -LiteralPath $script:ContractPath -Raw -Encoding utf8 | ConvertFrom-Json

function New-AngmooLauncherResult {
    param(
        [string]$Command,
        [string]$Project,
        [string]$Mode,
        [bool]$Ok,
        [string]$State,
        [int]$ExitCode,
        [AllowNull()][object]$ErrorCode,
        [string]$Message,
        [hashtable]$Details = @{}
    )
    return [pscustomobject][ordered]@{
        schema_version = [string]$script:Contract.result_schema
        timestamp = [DateTime]::UtcNow.ToString('o')
        command = $Command
        ok = $Ok
        state = $State
        exit_code = $ExitCode
        error_code = $ErrorCode
        message = $Message
        project = $Project
        mode = $Mode
        details = [pscustomobject]$Details
    }
}

function Get-AngmooExitCode {
    param([string]$Name)
    return [int]$script:Contract.exit_codes.$Name
}

function ConvertFrom-AngmooLauncherArguments {
    param([string[]]$Tokens)
    $parsed = [ordered]@{
        json = $false
        contributor = $false
        project_name = if ($env:COMPOSE_PROJECT_NAME) { $env:COMPOSE_PROJECT_NAME } else { [string]$script:Contract.default_project }
        port = if ($env:ANGMOO_PORT) { $env:ANGMOO_PORT } else { [string]$script:Contract.default_port }
        follow = $false
        tail = 200
        errors = [System.Collections.Generic.List[string]]::new()
    }
    for ($index = 0; $index -lt $Tokens.Count; $index++) {
        $token = $Tokens[$index]
        switch ($token.ToLowerInvariant()) {
            '--json' { $parsed.json = $true; continue }
            '-json' { $parsed.json = $true; continue }
            '--contributor' { $parsed.contributor = $true; continue }
            '-contributor' { $parsed.contributor = $true; continue }
            '--follow' { $parsed.follow = $true; continue }
            '-follow' { $parsed.follow = $true; continue }
            '--project-name' {
                if ($index + 1 -ge $Tokens.Count) { $parsed.errors.Add('missing_project_name'); continue }
                $index++; $parsed.project_name = $Tokens[$index]; continue
            }
            '-projectname' {
                if ($index + 1 -ge $Tokens.Count) { $parsed.errors.Add('missing_project_name'); continue }
                $index++; $parsed.project_name = $Tokens[$index]; continue
            }
            '--port' {
                if ($index + 1 -ge $Tokens.Count) { $parsed.errors.Add('missing_port'); continue }
                $index++; $parsed.port = $Tokens[$index]; continue
            }
            '-port' {
                if ($index + 1 -ge $Tokens.Count) { $parsed.errors.Add('missing_port'); continue }
                $index++; $parsed.port = $Tokens[$index]; continue
            }
            '--tail' {
                if ($index + 1 -ge $Tokens.Count) { $parsed.errors.Add('missing_tail'); continue }
                $index++
                $tailValue = 0
                if (-not [int]::TryParse($Tokens[$index], [ref]$tailValue) -or $tailValue -lt 0 -or $tailValue -gt 10000) {
                    $parsed.errors.Add('invalid_tail')
                } else { $parsed.tail = $tailValue }
                continue
            }
            '-tail' {
                if ($index + 1 -ge $Tokens.Count) { $parsed.errors.Add('missing_tail'); continue }
                $index++
                $tailValue = 0
                if (-not [int]::TryParse($Tokens[$index], [ref]$tailValue) -or $tailValue -lt 0 -or $tailValue -gt 10000) {
                    $parsed.errors.Add('invalid_tail')
                } else { $parsed.tail = $tailValue }
                continue
            }
            default {
                if (@($script:Contract.safety.forbidden_options) -contains $token.ToLowerInvariant()) {
                    $parsed.errors.Add("destructive_option:$token")
                } else {
                    $parsed.errors.Add("unknown_option:$token")
                }
            }
        }
    }
    if ($parsed.project_name -notmatch '^[a-z0-9][a-z0-9_-]*$') { $parsed.errors.Add('invalid_project_name') }
    $portValue = 0
    if (-not [int]::TryParse([string]$parsed.port, [ref]$portValue) -or $portValue -lt 1 -or $portValue -gt 65535) {
        $parsed.errors.Add('invalid_port')
    } else { $parsed.port = $portValue }
    return [pscustomobject]$parsed
}

function Invoke-AngmooDocker {
    param([string[]]$Arguments)
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if ($null -eq $docker) {
        return [pscustomobject]@{ exit_code = 127; output = @('docker command not found') }
    }
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = @(& $docker.Source @Arguments 2>&1 | ForEach-Object { [string]$_ })
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    return [pscustomobject]@{ exit_code = [int]$exitCode; output = $output }
}

function Get-AngmooComposeFiles {
    param([bool]$Contributor)
    $relativeFiles = if ($Contributor) { @($script:Contract.compose.contributor_files) } else { @($script:Contract.compose.release_files) }
    return @($relativeFiles | ForEach-Object { (Resolve-Path (Join-Path $script:LauncherRoot $_)).Path })
}

function Get-AngmooComposeArguments {
    param([string]$Project, [bool]$Contributor)
    $arguments = [System.Collections.Generic.List[string]]::new()
    $arguments.Add('compose')
    $arguments.Add('--project-directory'); $arguments.Add($script:LauncherRoot)
    $arguments.Add('--project-name'); $arguments.Add($Project)
    foreach ($file in (Get-AngmooComposeFiles -Contributor $Contributor)) {
        $arguments.Add('-f'); $arguments.Add($file)
    }
    return @($arguments)
}

function Invoke-AngmooCompose {
    param([string]$Project, [bool]$Contributor, [string[]]$Arguments)
    $all = [System.Collections.Generic.List[string]]::new()
    foreach ($item in (Get-AngmooComposeArguments -Project $Project -Contributor $Contributor)) { $all.Add($item) }
    foreach ($item in $Arguments) { $all.Add($item) }
    return Invoke-AngmooDocker -Arguments @($all)
}

function Get-AngmooFreeDiskGiB {
    # Pulls, layers, and volumes consume the Docker Desktop data drive, not
    # necessarily the checkout drive. The default Windows location follows
    # LOCALAPPDATA. A custom Docker data path can be declared explicitly.
    $diskPath = if ($env:ANGMOO_DOCKER_DATA_PATH) {
        $env:ANGMOO_DOCKER_DATA_PATH
    } elseif ($env:LOCALAPPDATA) {
        Join-Path $env:LOCALAPPDATA 'Docker'
    } else {
        $script:LauncherRoot
    }
    $root = [IO.Path]::GetPathRoot($diskPath)
    if (-not $root) { return $null }
    $driveName = $root.TrimEnd('\').TrimEnd(':')
    $drive = Get-PSDrive -Name $driveName -ErrorAction SilentlyContinue
    if ($null -eq $drive) { return $null }
    return [Math]::Round(([double]$drive.Free / 1GB), 2)
}

function Test-AngmooPortListening {
    param([int]$Port)
    try {
        $listeners = [Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
        return [bool]($listeners | Where-Object { $_.Port -eq $Port } | Select-Object -First 1)
    } catch { return $false }
}

function Test-AngmooOwnsPort {
    param([string]$Project, [bool]$Contributor, [int]$Port)
    $result = Invoke-AngmooCompose -Project $Project -Contributor $Contributor -Arguments @('port', 'frontend', '3000')
    if ($result.exit_code -ne 0) { return $false }
    return [bool]($result.output | Where-Object { $_ -match "(^|:)$Port$" } | Select-Object -First 1)
}

function Get-AngmooVolumeInventory {
    param([string]$Project)
    $result = Invoke-AngmooDocker -Arguments @('volume', 'ls', '--filter', "label=com.docker.compose.project=$Project", '--format', '{{.Name}}')
    if ($result.exit_code -ne 0) { return @() }
    return @($result.output | Where-Object { $_ -and $_.Trim() } | ForEach-Object { $_.Trim() })
}

function Test-AngmooReleaseImagesPresent {
    $backend = if ($env:ANGMOO_VERSION) { $env:ANGMOO_VERSION } else { 'v0.2.0' }
    $images = @(
        "ghcr.io/angmoo-tree/angmoo-backend:$backend",
        "ghcr.io/angmoo-tree/angmoo-frontend:$backend"
    )
    foreach ($image in $images) {
        $result = Invoke-AngmooDocker -Arguments @('image', 'inspect', $image)
        if ($result.exit_code -ne 0) { return $false }
    }
    return $true
}

function Invoke-AngmooPreflight {
    param([string]$Project, [bool]$Contributor, [int]$Port, [bool]$ForStart)
    $checks = [System.Collections.Generic.List[object]]::new()
    $dockerInfo = Invoke-AngmooDocker -Arguments @('info', '--format', '{{.ServerVersion}}')
    if ($dockerInfo.exit_code -ne 0) {
        return [pscustomobject]@{ ok = $false; degraded = $false; exit_code = (Get-AngmooExitCode 'container_engine_unavailable'); error_code = 'docker_engine_unavailable'; message = 'Docker Engine is unavailable.'; checks = @($checks) }
    }
    $checks.Add([pscustomobject]@{ name = 'docker_engine'; state = 'ready'; detail = 'reachable' })

    $composeVersion = Invoke-AngmooDocker -Arguments @('compose', 'version', '--short')
    if ($composeVersion.exit_code -ne 0) {
        return [pscustomobject]@{ ok = $false; degraded = $false; exit_code = (Get-AngmooExitCode 'container_engine_unavailable'); error_code = 'compose_unavailable'; message = 'Docker Compose is unavailable.'; checks = @($checks) }
    }
    $checks.Add([pscustomobject]@{ name = 'compose'; state = 'ready'; detail = ($composeVersion.output -join ' ').Trim() })

    $architecture = [string]$env:PROCESSOR_ARCHITECTURE
    if ($architecture -notmatch '^(AMD64|x86_64)$') {
        return [pscustomobject]@{ ok = $false; degraded = $false; exit_code = (Get-AngmooExitCode 'preflight_failed'); error_code = 'unsupported_architecture'; message = "Unsupported host architecture: $architecture"; checks = @($checks) }
    }
    $checks.Add([pscustomobject]@{ name = 'architecture'; state = 'ready'; detail = $architecture })

    $config = Invoke-AngmooCompose -Project $Project -Contributor $Contributor -Arguments @('config', '--quiet')
    if ($config.exit_code -ne 0) {
        return [pscustomobject]@{ ok = $false; degraded = $false; exit_code = (Get-AngmooExitCode 'preflight_failed'); error_code = 'compose_config_invalid'; message = 'Canonical Compose configuration is invalid.'; checks = @($checks); command_output = @($config.output) }
    }
    $checks.Add([pscustomobject]@{ name = 'compose_config'; state = 'ready'; detail = 'valid' })

    if (Test-AngmooPortListening -Port $Port) {
        if (-not (Test-AngmooOwnsPort -Project $Project -Contributor $Contributor -Port $Port)) {
            return [pscustomobject]@{ ok = $false; degraded = $false; exit_code = (Get-AngmooExitCode 'preflight_failed'); error_code = 'host_port_conflict'; message = "127.0.0.1:$Port is owned by another process or Compose project."; checks = @($checks) }
        }
        $checks.Add([pscustomobject]@{ name = 'host_port'; state = 'ready'; detail = 'owned_by_current_project' })
    } else {
        $checks.Add([pscustomobject]@{ name = 'host_port'; state = 'ready'; detail = 'available' })
    }

    $volumes = @(Get-AngmooVolumeInventory -Project $Project)
    $databaseVolume = "$($Project)_angmoo_postgresql_data"
    $secretVolume = "$($Project)_angmoo_runtime_secrets"
    $databasePresent = $volumes -contains $databaseVolume
    $secretPresent = $volumes -contains $secretVolume
    if ($databasePresent -and -not $secretPresent) {
        return [pscustomobject]@{ ok = $false; degraded = $false; exit_code = (Get-AngmooExitCode 'recovery_required'); error_code = 'credential_recovery_required'; message = 'The database volume exists but its persistent secret volume is missing.'; checks = @($checks); volumes = $volumes; secret_state = 'missing' }
    }
    $secretState = if ($secretPresent) { 'present' } else { 'missing' }
    $checks.Add([pscustomobject]@{ name = 'persistent_secret'; state = if ($databasePresent -and $secretPresent) { 'ready' } else { 'not_initialized' }; detail = $secretState })

    $freeGiB = Get-AngmooFreeDiskGiB
    $diskState = 'unknown'
    $diskMessage = 'Host disk could not be measured.'
    $degraded = $false
    if ($null -ne $freeGiB) {
        $freshRelease = (-not $Contributor) -and (-not (Test-AngmooReleaseImagesPresent))
        if ($Contributor) {
            $fail = [double]$script:Contract.disk_policy_gib.contributor_fail
            $warn = [double]$script:Contract.disk_policy_gib.contributor_warn
        } elseif ($freshRelease) {
            $fail = [double]$script:Contract.disk_policy_gib.release_fresh_fail
            $warn = [double]$script:Contract.disk_policy_gib.release_fresh_warn
        } else {
            $fail = [double]$script:Contract.disk_policy_gib.release_existing_critical
            $warn = $fail
        }
        if ($freeGiB -lt $fail) {
            return [pscustomobject]@{ ok = $false; degraded = $false; exit_code = (Get-AngmooExitCode 'preflight_failed'); error_code = 'runtime_disk_space_low'; message = "Host disk is critically low: $freeGiB GiB free."; checks = @($checks); free_disk_gib = $freeGiB; secret_state = $secretState; volumes = $volumes }
        }
        if ($freeGiB -lt $warn) {
            $diskState = 'warning'; $diskMessage = "$freeGiB GiB free; this mode recommends at least $warn GiB before a large pull or build."; $degraded = $true
        } else {
            $diskState = 'ready'; $diskMessage = "$freeGiB GiB free"
        }
    }
    $checks.Add([pscustomobject]@{ name = 'host_disk'; state = $diskState; detail = $diskMessage })
    return [pscustomobject]@{ ok = $true; degraded = $degraded; exit_code = 0; error_code = $null; message = 'Host preflight passed.'; checks = @($checks); free_disk_gib = $freeGiB; secret_state = $secretState; volumes = $volumes }
}

function Get-AngmooComposeStatus {
    param([string]$Project, [bool]$Contributor)
    $result = Invoke-AngmooCompose -Project $Project -Contributor $Contributor -Arguments @('ps', '--all', '--format', 'json')
    if ($result.exit_code -ne 0) { return [pscustomobject]@{ state = 'failed'; services = @(); output = @($result.output) } }
    $raw = ($result.output -join "`n").Trim()
    if (-not $raw) { return [pscustomobject]@{ state = 'stopped'; services = @(); output = @() } }
    $services = @()
    try {
        $parsed = $raw | ConvertFrom-Json
        $services = @($parsed)
    } catch {
        foreach ($line in $result.output) {
            if ($line.Trim()) {
                try { $services += ($line | ConvertFrom-Json) } catch { }
            }
        }
    }
    $required = @($script:Contract.compose.required_services)
    $running = @($services | Where-Object { ([string]$_.State).ToLowerInvariant() -eq 'running' })
    $healthFailures = @($running | Where-Object { $_.Health -and ([string]$_.Health).ToLowerInvariant() -notin @('healthy', '') })
    if ($services.Count -eq 0) { $state = 'stopped' }
    elseif ($running.Count -eq $required.Count -and $healthFailures.Count -eq 0) { $state = 'ready' }
    elseif ($running.Count -gt 0) { $state = 'degraded' }
    else { $state = 'stopped' }
    $records = @($services | ForEach-Object {
        [pscustomobject]@{
            service = [string]$_.Service
            state = [string]$_.State
            health = if ($_.Health) { [string]$_.Health } else { 'not_reported' }
            image = [string]$_.Image
        }
    })
    return [pscustomobject]@{ state = $state; services = $records; output = @() }
}

function Get-AngmooLockName {
    param([string]$Project)
    $identity = "$($script:LauncherRoot.ToLowerInvariant())|$($Project.ToLowerInvariant())"
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $digest = $sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($identity)) } finally { $sha.Dispose() }
    $hex = -join ($digest | ForEach-Object { $_.ToString('x2') })
    return "Local\AngmooLauncher-$hex"
}

function Invoke-AngmooLockedLifecycle {
    param([string]$Command, [string]$Project, [bool]$Contributor, [int]$Port)
    $mutex = [Threading.Mutex]::new($false, (Get-AngmooLockName -Project $Project))
    $owns = $false
    try {
        try { $owns = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $owns = $true }
        if (-not $owns) {
            return New-AngmooLauncherResult -Command $Command -Project $Project -Mode $(if ($Contributor) { 'contributor' } else { 'release' }) -Ok $false -State 'failed' -ExitCode (Get-AngmooExitCode 'recovery_required') -ErrorCode 'lifecycle_lock_held' -Message 'Another lifecycle command owns this installation lock.'
        }
        if ($Command -eq 'stop') {
            $before = Get-AngmooComposeStatus -Project $Project -Contributor $Contributor
            if ($before.state -eq 'stopped') {
                return New-AngmooLauncherResult -Command $Command -Project $Project -Mode $(if ($Contributor) { 'contributor' } else { 'release' }) -Ok $true -State 'stopped' -ExitCode 0 -ErrorCode $null -Message 'Angmoo is already stopped; volumes were preserved.' -Details @{ services = $before.services; volumes_preserved = $true }
            }
            $stopped = Invoke-AngmooCompose -Project $Project -Contributor $Contributor -Arguments @('stop', '--timeout', [string]$script:Contract.timeouts_seconds.stop)
            if ($stopped.exit_code -ne 0) {
                return New-AngmooLauncherResult -Command $Command -Project $Project -Mode $(if ($Contributor) { 'contributor' } else { 'release' }) -Ok $false -State 'failed' -ExitCode (Get-AngmooExitCode 'recovery_required') -ErrorCode 'lifecycle_stop_failed' -Message 'Compose stop failed; inspect logs before retrying.' -Details @{ compose_output = @($stopped.output); volumes_preserved = $true }
            }
            return New-AngmooLauncherResult -Command $Command -Project $Project -Mode $(if ($Contributor) { 'contributor' } else { 'release' }) -Ok $true -State 'stopped' -ExitCode 0 -ErrorCode $null -Message 'Angmoo stopped; named volumes were preserved.' -Details @{ volumes_preserved = $true }
        }

        if ($Command -eq 'restart') {
            $stopped = Invoke-AngmooCompose -Project $Project -Contributor $Contributor -Arguments @('stop', '--timeout', [string]$script:Contract.timeouts_seconds.stop)
            if ($stopped.exit_code -ne 0) {
                return New-AngmooLauncherResult -Command $Command -Project $Project -Mode $(if ($Contributor) { 'contributor' } else { 'release' }) -Ok $false -State 'failed' -ExitCode (Get-AngmooExitCode 'recovery_required') -ErrorCode 'lifecycle_stop_failed' -Message 'Compose stop failed during restart.' -Details @{ compose_output = @($stopped.output); volumes_preserved = $true }
            }
        }

        $preflight = Invoke-AngmooPreflight -Project $Project -Contributor $Contributor -Port $Port -ForStart $true
        if (-not $preflight.ok) {
            return New-AngmooLauncherResult -Command $Command -Project $Project -Mode $(if ($Contributor) { 'contributor' } else { 'release' }) -Ok $false -State 'failed' -ExitCode $preflight.exit_code -ErrorCode $preflight.error_code -Message $preflight.message -Details @{ checks = @($preflight.checks) }
        }
        if ($Command -eq 'start') {
            $current = Get-AngmooComposeStatus -Project $Project -Contributor $Contributor
            if ($current.state -eq 'ready' -and (Test-AngmooOwnsPort -Project $Project -Contributor $Contributor -Port $Port)) {
                return New-AngmooLauncherResult -Command $Command -Project $Project -Mode $(if ($Contributor) { 'contributor' } else { 'release' }) -Ok $true -State 'ready' -ExitCode 0 -ErrorCode $null -Message 'Angmoo is already ready; no container was recreated.' -Details @{ checks = @($preflight.checks); services = $current.services; idempotent_no_op = $true; volumes_preserved = $true; watch_command = $(if ($Contributor) { 'docker compose -f compose.yml -f compose.dev.yml up --watch' } else { $null }) }
            }
        }
        $timeout = if ($Contributor) { [int]$script:Contract.timeouts_seconds.start_contributor } else { [int]$script:Contract.timeouts_seconds.start_release }
        $upArguments = [System.Collections.Generic.List[string]]::new()
        $upArguments.Add('up'); $upArguments.Add('-d')
        if ($Contributor) { $upArguments.Add('--build') }
        $upArguments.Add('--wait'); $upArguments.Add('--wait-timeout'); $upArguments.Add([string]$timeout)
        $started = Invoke-AngmooCompose -Project $Project -Contributor $Contributor -Arguments @($upArguments)
        if ($started.exit_code -ne 0) {
            return New-AngmooLauncherResult -Command $Command -Project $Project -Mode $(if ($Contributor) { 'contributor' } else { 'release' }) -Ok $false -State 'failed' -ExitCode (Get-AngmooExitCode 'startup_failed') -ErrorCode 'runtime_start_timeout' -Message 'Compose did not make the complete stack ready before the startup timeout.' -Details @{ checks = @($preflight.checks); compose_output = @($started.output); volumes_preserved = $true }
        }
        $after = Get-AngmooComposeStatus -Project $Project -Contributor $Contributor
        return New-AngmooLauncherResult -Command $Command -Project $Project -Mode $(if ($Contributor) { 'contributor' } else { 'release' }) -Ok $true -State $after.state -ExitCode 0 -ErrorCode $null -Message $(if ($Command -eq 'restart') { 'Angmoo restarted with existing named volumes.' } else { 'Angmoo is ready.' }) -Details @{ checks = @($preflight.checks); services = $after.services; volumes_preserved = $true; watch_command = $(if ($Contributor) { 'docker compose -f compose.yml -f compose.dev.yml up --watch' } else { $null }) }
    } finally {
        if ($owns) { try { $mutex.ReleaseMutex() } catch { } }
        $mutex.Dispose()
    }
}

function Invoke-AngmooLauncher {
    [CmdletBinding()]
    param([string]$Command, [string[]]$Arguments = @())
    $options = ConvertFrom-AngmooLauncherArguments -Tokens $Arguments
    $normalizedCommand = $Command.ToLowerInvariant()
    $mode = if ($options.contributor) { 'contributor' } else { 'release' }
    $hadPortEnvironment = Test-Path Env:ANGMOO_PORT
    $previousPortEnvironment = $env:ANGMOO_PORT
    $env:ANGMOO_PORT = [string]$options.port
    try {
    if ($normalizedCommand -eq 'help') {
        $result = New-AngmooLauncherResult -Command 'help' -Project $options.project_name -Mode $mode -Ok $true -State 'not_started' -ExitCode 0 -ErrorCode $null -Message 'Usage: .\angmoo.ps1 <start|stop|restart|status|logs|doctor> [--json] [--contributor] [--project-name NAME] [--port PORT]'
        return [pscustomobject]@{ result = $result; json_requested = $options.json }
    }
    if ($options.errors.Count -gt 0) {
        $destructive = [bool]($options.errors | Where-Object { $_ -like 'destructive_option:*' })
        $result = New-AngmooLauncherResult -Command $normalizedCommand -Project $options.project_name -Mode $mode -Ok $false -State 'failed' -ExitCode $(if ($destructive) { Get-AngmooExitCode 'destructive_command_blocked' } else { Get-AngmooExitCode 'invalid_argument' }) -ErrorCode $(if ($destructive) { 'destructive_command_blocked' } else { 'launcher_invalid_argument' }) -Message ($options.errors -join ', ')
        return [pscustomobject]@{ result = $result; json_requested = $options.json }
    }
    if (@($script:Contract.commands) -notcontains $normalizedCommand) {
        $result = New-AngmooLauncherResult -Command $normalizedCommand -Project $options.project_name -Mode $mode -Ok $false -State 'failed' -ExitCode (Get-AngmooExitCode 'invalid_argument') -ErrorCode 'launcher_invalid_argument' -Message "Unsupported command: $normalizedCommand"
        return [pscustomobject]@{ result = $result; json_requested = $options.json }
    }
    if ($normalizedCommand -in @('start', 'stop', 'restart')) {
        $result = Invoke-AngmooLockedLifecycle -Command $normalizedCommand -Project $options.project_name -Contributor $options.contributor -Port $options.port
        return [pscustomobject]@{ result = $result; json_requested = $options.json }
    }
    if ($normalizedCommand -eq 'status') {
        $engine = Invoke-AngmooDocker -Arguments @('info', '--format', '{{.ServerVersion}}')
        if ($engine.exit_code -ne 0) {
            $result = New-AngmooLauncherResult -Command $normalizedCommand -Project $options.project_name -Mode $mode -Ok $false -State 'failed' -ExitCode (Get-AngmooExitCode 'container_engine_unavailable') -ErrorCode 'docker_engine_unavailable' -Message 'Docker Engine is unavailable.'
        } else {
            $status = Get-AngmooComposeStatus -Project $options.project_name -Contributor $options.contributor
            $result = New-AngmooLauncherResult -Command $normalizedCommand -Project $options.project_name -Mode $mode -Ok ($status.state -ne 'failed') -State $status.state -ExitCode $(if ($status.state -eq 'failed') { Get-AngmooExitCode 'preflight_failed' } else { 0 }) -ErrorCode $(if ($status.state -eq 'failed') { 'compose_config_invalid' } else { $null }) -Message "Angmoo state: $($status.state)." -Details @{ services = $status.services }
        }
        return [pscustomobject]@{ result = $result; json_requested = $options.json }
    }
    if ($normalizedCommand -eq 'doctor') {
        $preflight = Invoke-AngmooPreflight -Project $options.project_name -Contributor $options.contributor -Port $options.port -ForStart $false
        if (-not $preflight.ok) {
            $result = New-AngmooLauncherResult -Command $normalizedCommand -Project $options.project_name -Mode $mode -Ok $false -State 'failed' -ExitCode $preflight.exit_code -ErrorCode $preflight.error_code -Message $preflight.message -Details @{ checks = @($preflight.checks) }
        } else {
            $status = Get-AngmooComposeStatus -Project $options.project_name -Contributor $options.contributor
            $isDegraded = $preflight.degraded -or $status.state -notin @('ready', 'stopped')
            $result = New-AngmooLauncherResult -Command $normalizedCommand -Project $options.project_name -Mode $mode -Ok (-not $isDegraded) -State $(if ($isDegraded) { 'degraded' } else { $status.state }) -ExitCode $(if ($isDegraded) { Get-AngmooExitCode 'doctor_degraded' } else { 0 }) -ErrorCode $(if ($isDegraded) { 'doctor_degraded' } else { $null }) -Message $(if ($isDegraded) { 'Doctor found a degraded host or Compose condition.' } else { 'Doctor checks passed.' }) -Details @{ checks = @($preflight.checks); services = $status.services; free_disk_gib = $preflight.free_disk_gib; secret_state = $preflight.secret_state; volume_count = @($preflight.volumes).Count }
        }
        return [pscustomobject]@{ result = $result; json_requested = $options.json }
    }
    $logArguments = @('logs', '--tail', [string]$options.tail)
    if ($options.follow) { $logArguments += '--follow' }
    $logs = Invoke-AngmooCompose -Project $options.project_name -Contributor $options.contributor -Arguments $logArguments
    $result = New-AngmooLauncherResult -Command $normalizedCommand -Project $options.project_name -Mode $mode -Ok ($logs.exit_code -eq 0) -State $(if ($logs.exit_code -eq 0) { 'observed' } else { 'failed' }) -ExitCode $(if ($logs.exit_code -eq 0) { 0 } else { Get-AngmooExitCode 'preflight_failed' }) -ErrorCode $(if ($logs.exit_code -eq 0) { $null } else { 'compose_config_invalid' }) -Message $(if ($logs.exit_code -eq 0) { 'Compose logs collected.' } else { 'Compose logs could not be read.' }) -Details @{ log_lines = @($logs.output) }
    return [pscustomobject]@{ result = $result; json_requested = $options.json }
    } finally {
        if ($hadPortEnvironment) {
            $env:ANGMOO_PORT = $previousPortEnvironment
        } else {
            Remove-Item Env:ANGMOO_PORT -ErrorAction SilentlyContinue
        }
    }
}

function Write-AngmooLauncherHumanResult {
    param([Parameter(Mandatory = $true)]$Result)
    Write-Output "[$($Result.state)] $($Result.message)"
    Write-Output "command=$($Result.command) project=$($Result.project) mode=$($Result.mode) exit_code=$($Result.exit_code)"
    if ($Result.error_code) { Write-Output "error_code=$($Result.error_code)" }
    $checksProperty = $Result.details.PSObject.Properties['checks']
    if ($null -ne $checksProperty -and $checksProperty.Value) {
        foreach ($check in @($checksProperty.Value)) { Write-Output "check=$($check.name) state=$($check.state) detail=$($check.detail)" }
    }
    $servicesProperty = $Result.details.PSObject.Properties['services']
    if ($null -ne $servicesProperty -and $servicesProperty.Value) {
        foreach ($service in @($servicesProperty.Value)) { Write-Output "service=$($service.service) state=$($service.state) health=$($service.health)" }
    }
    $logsProperty = $Result.details.PSObject.Properties['log_lines']
    if ($null -ne $logsProperty -and $logsProperty.Value) {
        foreach ($line in @($logsProperty.Value)) { Write-Output $line }
    }
}

Export-ModuleMember -Function Invoke-AngmooLauncher, Write-AngmooLauncherHumanResult
