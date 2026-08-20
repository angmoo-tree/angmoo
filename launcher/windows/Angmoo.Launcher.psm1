Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:LauncherRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script:ContractPath = Join-Path $script:LauncherRoot 'launcher\contract\local-launcher-v1.json'
$script:Contract = Get-Content -LiteralPath $script:ContractPath -Raw -Encoding utf8 | ConvertFrom-Json
$script:InProcessMode = $false

function Protect-AngmooDiagnosticText {
    param([AllowNull()][string]$Value)
    if ($null -eq $Value) { return $null }
    $redacted = $Value
    $redacted = $redacted -replace '\bAIza[0-9A-Za-z_-]{20,}\b', '[REDACTED_API_KEY]'
    $redacted = $redacted -replace '\bsk-[A-Za-z0-9_-]{20,}\b', '[REDACTED_API_KEY]'
    $redacted = $redacted -replace '(?i)\b(APP_SECRET|POSTGRES(?:QL)?_PASSWORD|NEO4J_PASSWORD|API_KEY|AUTHORIZATION|SESSION_TOKEN)\s*[:=]\s*[^\s,;]+', '$1=[REDACTED]'
    foreach ($secretName in @('APP_SECRET', 'POSTGRES_PASSWORD', 'NEO4J_PASSWORD')) {
        $secret = [Environment]::GetEnvironmentVariable($secretName)
        if ($secret) { $redacted = $redacted.Replace($secret, '[REDACTED]') }
    }
    return $redacted
}

function Protect-AngmooDiagnosticValue {
    param(
        [AllowNull()][object]$Value,
        [string]$FieldName = ''
    )
    $normalizedField = $FieldName.Replace('-', '_').ToLowerInvariant()
    if ($normalizedField -in @(
        'api_key', 'apikey', 'authorization', 'token', 'access_token',
        'refresh_token', 'secret', 'password', 'app_secret', 'session_token',
        'encrypted_api_key', 'credential_payload', 'full_prompt',
        'provider_response', 'private_chat', 'sns_content', 'media_original'
    )) { return '[REDACTED]' }
    if ($null -eq $Value) { return $null }
    if ($Value -is [string]) { return Protect-AngmooDiagnosticText -Value $Value }
    if ($Value -is [Collections.IDictionary]) {
        $safe = [ordered]@{}
        foreach ($key in $Value.Keys) {
            $safe[[string]$key] = Protect-AngmooDiagnosticValue -Value $Value[$key] -FieldName ([string]$key)
        }
        return [pscustomobject]$safe
    }
    if ($Value -is [Management.Automation.PSCustomObject]) {
        $safe = [ordered]@{}
        foreach ($property in $Value.PSObject.Properties) {
            $safe[$property.Name] = Protect-AngmooDiagnosticValue -Value $property.Value -FieldName $property.Name
        }
        return [pscustomobject]$safe
    }
    if ($Value -is [Collections.IEnumerable] -and $Value -isnot [string]) {
        return @($Value | ForEach-Object { Protect-AngmooDiagnosticValue -Value $_ })
    }
    return $Value
}

function Test-AngmooDiagnosticSanitizer {
    $canary = 'AIza' + ('Z' * 24)
    $result = Protect-AngmooDiagnosticValue -Value ([ordered]@{
        api_key = $canary
        message = (('APP' + '_SECRET=') + $canary)
    })
    $serialized = $result | ConvertTo-Json -Depth 5 -Compress
    return -not $serialized.Contains($canary)
}

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
        message = Protect-AngmooDiagnosticText -Value $Message
        project = $Project
        mode = $Mode
        details = Protect-AngmooDiagnosticValue -Value $Details
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
        in_process = $false
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
            '--in-process' { $parsed.in_process = $true; continue }
            '-inprocess' { $parsed.in_process = $true; continue }
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
    if ($script:InProcessMode) {
        $relativeFiles = @($relativeFiles) + @([string]$script:Contract.compose.in_process_file)
    }
    return @($relativeFiles | ForEach-Object { (Resolve-Path (Join-Path $script:LauncherRoot $_)).Path })
}

function Get-AngmooRequiredServices {
    if ($script:InProcessMode) {
        return @($script:Contract.compose.in_process_required_services)
    }
    return @($script:Contract.compose.required_services)
}

function Get-AngmooWatchCommand {
    param([bool]$Contributor)
    if (-not $Contributor) { return $null }
    if ($script:InProcessMode) {
        return 'docker compose -f compose.yml -f compose.dev.yml -f compose.in-process.yml up --watch'
    }
    return 'docker compose -f compose.yml -f compose.dev.yml up --watch'
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

function Stop-AngmooExternalWorkersForInProcessMode {
    param([string]$Project, [bool]$Contributor)
    if (-not $script:InProcessMode) {
        return [pscustomobject]@{ exit_code = 0; output = @() }
    }
    $all = [System.Collections.Generic.List[string]]::new()
    foreach ($item in (Get-AngmooComposeArguments -Project $Project -Contributor $Contributor)) { $all.Add($item) }
    $all.Add('--profile'); $all.Add('external-workers')
    $all.Add('stop'); $all.Add('--timeout'); $all.Add([string]$script:Contract.timeouts_seconds.stop)
    $all.Add('scheduler'); $all.Add('projector')
    return Invoke-AngmooDocker -Arguments @($all)
}

function Test-AngmooInProcessComponentsReady {
    param([string]$Project, [bool]$Contributor)
    if (-not $script:InProcessMode) { return $true }
    $application = Get-AngmooApplicationStatus -Project $Project -Contributor $Contributor
    if ($application.state -ne 'ready' -or $null -eq $application.payload) { return $false }
    return (
        [string]$application.payload.scheduler.state -eq 'running' -and
        [string]$application.payload.projector.state -in @('ready', 'degraded')
    )
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
    $backend = if ($env:ANGMOO_VERSION) { $env:ANGMOO_VERSION } else { 'v0.3.0' }
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
    $required = @(Get-AngmooRequiredServices)
    $relevant = @($services | Where-Object { $required -contains [string]$_.Service })
    $running = @($relevant | Where-Object { ([string]$_.State).ToLowerInvariant() -eq 'running' })
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

function Get-AngmooApplicationStatus {
    param([string]$Project, [bool]$Contributor)
    $result = Invoke-AngmooCompose -Project $Project -Contributor $Contributor -Arguments @(
        'exec', '-T', 'backend', '/usr/local/bin/angmoo-backend-entrypoint', 'diagnostics'
    )
    if ($result.exit_code -ne 0) {
        return [pscustomobject]@{
            state = 'unknown'
            error_code = 'application_status_unavailable'
            payload = $null
        }
    }
    foreach ($line in @($result.output | Select-Object -Last 5)) {
        if (-not $line.Trim().StartsWith('{')) { continue }
        try {
            $payload = $line | ConvertFrom-Json
            if ($payload.schema_version -eq 'local-runtime-status-v1') {
                return [pscustomobject]@{
                    state = [string]$payload.installation_state
                    error_code = $null
                    payload = Protect-AngmooDiagnosticValue -Value $payload
                }
            }
        } catch { }
    }
    return [pscustomobject]@{
        state = 'unknown'
        error_code = 'application_status_unavailable'
        payload = $null
    }
}

function Get-AngmooDockerStorageStatus {
    $result = Invoke-AngmooDocker -Arguments @('system', 'df', '--format', '{{json .}}')
    if ($result.exit_code -ne 0) {
        return [pscustomobject]@{
            state = 'unknown'
            error_code = 'docker_usage_unavailable'
            records = @()
        }
    }
    $records = [System.Collections.Generic.List[object]]::new()
    foreach ($line in $result.output) {
        if (-not $line.Trim()) { continue }
        try {
            $item = $line | ConvertFrom-Json
            $records.Add([pscustomobject][ordered]@{
                type = [string]$item.Type
                total_count = [string]$item.TotalCount
                active_count = [string]$item.Active
                size = [string]$item.Size
                reclaimable = [string]$item.Reclaimable
            })
        } catch { }
    }
    return [pscustomobject]@{
        state = if ($records.Count -gt 0) { 'ready' } else { 'unknown' }
        error_code = if ($records.Count -gt 0) { $null } else { 'docker_usage_unavailable' }
        records = @($records)
    }
}

function Get-AngmooContainerResourceStatus {
    param([string]$Project, [bool]$Contributor)
    $measuredAt = [DateTime]::UtcNow.ToString('o')
    $compose = Invoke-AngmooCompose -Project $Project -Contributor $Contributor -Arguments @('ps', '--all', '--format', 'json')
    $containers = @()
    if ($compose.exit_code -eq 0) {
        $raw = ($compose.output -join "`n").Trim()
        if ($raw) {
            try { $containers = @($raw | ConvertFrom-Json) } catch {
                foreach ($line in $compose.output) {
                    if ($line.Trim()) {
                        try { $containers += ($line | ConvertFrom-Json) } catch { }
                    }
                }
            }
        }
    }
    $references = @($containers | ForEach-Object {
        if ($_.Name) { [string]$_.Name } elseif ($_.ID) { [string]$_.ID }
    } | Where-Object { $_ })
    $statsByName = @{}
    if ($references.Count -gt 0) {
        $statsArguments = @('stats', '--no-stream', '--format', '{{json .}}') + $references
        $stats = Invoke-AngmooDocker -Arguments $statsArguments
        if ($stats.exit_code -eq 0) {
            foreach ($line in $stats.output) {
                try {
                    $item = $line | ConvertFrom-Json
                    if ($item.Name) { $statsByName[[string]$item.Name] = $item }
                } catch { }
            }
        }
    }
    $inspectByName = @{}
    if ($references.Count -gt 0) {
        $inspectArguments = @(
            'inspect', '--format',
            '{{json dict "Name" .Name "RestartCount" .RestartCount "Image" .Image}}'
        ) + $references
        $inspect = Invoke-AngmooDocker -Arguments $inspectArguments
        if ($inspect.exit_code -eq 0) {
            foreach ($line in $inspect.output) {
                try {
                    $item = $line | ConvertFrom-Json
                    if ($item.Name) { $inspectByName[[string]$item.Name.TrimStart('/')] = $item }
                } catch { }
            }
        }
    }
    $records = [System.Collections.Generic.List[object]]::new()
    foreach ($service in @(Get-AngmooRequiredServices)) {
        $container = $containers | Where-Object { [string]$_.Service -eq [string]$service } | Select-Object -First 1
        $containerReference = if ($null -ne $container -and $container.Name) { [string]$container.Name } elseif ($null -ne $container -and $container.ID) { [string]$container.ID } else { '' }
        if (-not $containerReference.Trim()) {
            $records.Add([pscustomobject]@{
                service = [string]$service
                state = 'unknown'
                cpu_percent = 'unknown'
                memory_usage = 'unknown'
                restart_count = 'unknown'
                image_digest = 'unknown'
                measured_at = $measuredAt
            })
            continue
        }
        $cpu = 'unknown'; $memory = 'unknown'
        $statsPayload = $statsByName[$containerReference]
        if ($null -ne $statsPayload) {
            if ($statsPayload.CPUPerc) { $cpu = [string]$statsPayload.CPUPerc }
            if ($statsPayload.MemUsage) { $memory = [string]$statsPayload.MemUsage }
        }
        $restartCount = 'unknown'; $imageDigest = 'unknown'
        $inspectPayload = $inspectByName[$containerReference]
        if ($null -ne $inspectPayload) {
            if ($null -ne $inspectPayload.RestartCount) { $restartCount = [string]$inspectPayload.RestartCount }
            if ($inspectPayload.Image) {
                $image = [string]$inspectPayload.Image
                $imageDigest = $image.Substring(0, [Math]::Min(19, $image.Length))
            }
        }
        $records.Add([pscustomobject]@{
            service = [string]$service
            state = 'measured'
            cpu_percent = $cpu
            memory_usage = $memory
            restart_count = $restartCount
            image_digest = $imageDigest
            measured_at = $measuredAt
        })
    }
    return @($records)
}

function Get-AngmooHostDiagnostics {
    param([string]$Project, [bool]$Contributor, [bool]$IncludeResources)
    $storage = Get-AngmooDockerStorageStatus
    return [pscustomobject][ordered]@{
        free_disk_gib = Get-AngmooFreeDiskGiB
        named_volumes = @(Get-AngmooVolumeInventory -Project $Project)
        docker_storage = $storage
        container_resources = if ($IncludeResources) {
            @(Get-AngmooContainerResourceStatus -Project $Project -Contributor $Contributor)
        } else { @() }
    }
}

function Add-AngmooApplicationChecks {
    param(
        [System.Collections.Generic.List[object]]$Checks,
        [AllowNull()][object]$Application
    )
    if ($null -eq $Application -or $Application.state -eq 'unknown' -or $null -eq $Application.payload) {
        $Checks.Add([pscustomobject]@{
            name = 'application_status'
            state = 'unknown'
            detail = 'application_status_unavailable'
        })
        return
    }
    $payload = $Application.payload
    $Checks.Add([pscustomobject]@{
        name = 'application_status'
        state = [string]$payload.installation_state
        detail = [string]$payload.schema_version
    })
    $Checks.Add([pscustomobject]@{
        name = 'migration'
        state = [string]$payload.migration.state
        detail = "$($payload.migration.current_revision)/$($payload.migration.head_revision)"
    })
    $Checks.Add([pscustomobject]@{
        name = 'owner'
        state = if ($payload.owner.bootstrap_state -eq 'claimed') { 'ready' } else { [string]$payload.owner.bootstrap_state }
        detail = "worlds=$($payload.owner.registered_world_count) active_characters=$($payload.owner.active_world_character_count)"
    })
    $Checks.Add([pscustomobject]@{
        name = 'scheduler'
        state = [string]$payload.scheduler.state
        detail = "epoch=$($payload.scheduler.fencing_epoch)"
    })
    $Checks.Add([pscustomobject]@{
        name = 'projector'
        state = [string]$payload.projector.state
        detail = "pending=$($payload.projector.pending_count) retry=$($payload.projector.retry_count) dead=$($payload.projector.dead_letter_count)"
    })
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
        $parkedWorkers = Stop-AngmooExternalWorkersForInProcessMode -Project $Project -Contributor $Contributor
        if ($parkedWorkers.exit_code -ne 0) {
            return New-AngmooLauncherResult -Command $Command -Project $Project -Mode $(if ($Contributor) { 'contributor' } else { 'release' }) -Ok $false -State 'failed' -ExitCode (Get-AngmooExitCode 'recovery_required') -ErrorCode 'lifecycle_stop_failed' -Message 'External scheduler or projector could not be parked before in-process startup.' -Details @{ compose_output = @($parkedWorkers.output); volumes_preserved = $true }
        }
        if ($Command -eq 'start') {
            $current = Get-AngmooComposeStatus -Project $Project -Contributor $Contributor
            if (
                $current.state -eq 'ready' -and
                (Test-AngmooOwnsPort -Project $Project -Contributor $Contributor -Port $Port) -and
                (Test-AngmooInProcessComponentsReady -Project $Project -Contributor $Contributor)
            ) {
                return New-AngmooLauncherResult -Command $Command -Project $Project -Mode $(if ($Contributor) { 'contributor' } else { 'release' }) -Ok $true -State 'ready' -ExitCode 0 -ErrorCode $null -Message 'Angmoo is already ready; no container was recreated.' -Details @{ checks = @($preflight.checks); services = $current.services; idempotent_no_op = $true; volumes_preserved = $true; watch_command = (Get-AngmooWatchCommand -Contributor $Contributor) }
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
        return New-AngmooLauncherResult -Command $Command -Project $Project -Mode $(if ($Contributor) { 'contributor' } else { 'release' }) -Ok $true -State $after.state -ExitCode 0 -ErrorCode $null -Message $(if ($Command -eq 'restart') { 'Angmoo restarted with existing named volumes.' } else { 'Angmoo is ready.' }) -Details @{ checks = @($preflight.checks); services = $after.services; volumes_preserved = $true; watch_command = (Get-AngmooWatchCommand -Contributor $Contributor) }
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
    $script:InProcessMode = [bool]$options.in_process
    $hadPortEnvironment = Test-Path Env:ANGMOO_PORT
    $previousPortEnvironment = $env:ANGMOO_PORT
    $env:ANGMOO_PORT = [string]$options.port
    try {
    if ($normalizedCommand -eq 'help') {
        $result = New-AngmooLauncherResult -Command 'help' -Project $options.project_name -Mode $mode -Ok $true -State 'not_started' -ExitCode 0 -ErrorCode $null -Message 'Usage: .\angmoo.ps1 <start|stop|restart|status|logs|doctor> [--json] [--contributor] [--in-process] [--project-name NAME] [--port PORT]'
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
            $application = if ($status.state -in @('ready', 'degraded')) {
                Get-AngmooApplicationStatus -Project $options.project_name -Contributor $options.contributor
            } else {
                [pscustomobject]@{ state = 'unknown'; error_code = 'application_status_unavailable'; payload = $null }
            }
            $hostDiagnostics = Get-AngmooHostDiagnostics -Project $options.project_name -Contributor $options.contributor -IncludeResources ($status.state -in @('ready', 'degraded'))
            $aggregateState = $status.state
            if ($status.state -eq 'ready' -and $application.state -notin @('ready', 'unknown')) { $aggregateState = 'degraded' }
            $result = New-AngmooLauncherResult -Command $normalizedCommand -Project $options.project_name -Mode $mode -Ok ($status.state -ne 'failed') -State $aggregateState -ExitCode $(if ($status.state -eq 'failed') { Get-AngmooExitCode 'preflight_failed' } else { 0 }) -ErrorCode $(if ($status.state -eq 'failed') { 'compose_config_invalid' } else { $null }) -Message "Angmoo state: $aggregateState." -Details @{ services = $status.services; application = $application; host = $hostDiagnostics }
        }
        return [pscustomobject]@{ result = $result; json_requested = $options.json }
    }
    if ($normalizedCommand -eq 'doctor') {
        $preflight = Invoke-AngmooPreflight -Project $options.project_name -Contributor $options.contributor -Port $options.port -ForStart $false
        if (-not $preflight.ok) {
            $result = New-AngmooLauncherResult -Command $normalizedCommand -Project $options.project_name -Mode $mode -Ok $false -State 'failed' -ExitCode $preflight.exit_code -ErrorCode $preflight.error_code -Message $preflight.message -Details @{ checks = @($preflight.checks) }
        } else {
            $status = Get-AngmooComposeStatus -Project $options.project_name -Contributor $options.contributor
            $application = if ($status.state -in @('ready', 'degraded')) {
                Get-AngmooApplicationStatus -Project $options.project_name -Contributor $options.contributor
            } else {
                [pscustomobject]@{ state = 'unknown'; error_code = 'application_status_unavailable'; payload = $null }
            }
            $checks = [System.Collections.Generic.List[object]]::new()
            foreach ($check in @($preflight.checks)) { $checks.Add($check) }
            Add-AngmooApplicationChecks -Checks $checks -Application $application
            $privacyReady = Test-AngmooDiagnosticSanitizer
            $checks.Add([pscustomobject]@{
                name = 'privacy'
                state = if ($privacyReady) { 'ready' } else { 'failed' }
                detail = if ($privacyReady) { 'sanitizer_canary_absent' } else { 'diagnostic_redaction_failed' }
            })
            $hostDiagnostics = Get-AngmooHostDiagnostics -Project $options.project_name -Contributor $options.contributor -IncludeResources ($status.state -in @('ready', 'degraded'))
            $applicationDegraded = $status.state -eq 'ready' -and $application.state -notin @('ready')
            $isDegraded = $preflight.degraded -or $status.state -notin @('ready', 'stopped') -or $applicationDegraded -or (-not $privacyReady)
            $result = New-AngmooLauncherResult -Command $normalizedCommand -Project $options.project_name -Mode $mode -Ok (-not $isDegraded) -State $(if ($isDegraded) { 'degraded' } else { $status.state }) -ExitCode $(if ($isDegraded) { Get-AngmooExitCode 'doctor_degraded' } else { 0 }) -ErrorCode $(if ($isDegraded) { 'doctor_degraded' } else { $null }) -Message $(if ($isDegraded) { 'Doctor found a degraded host or Compose condition.' } else { 'Doctor checks passed.' }) -Details @{ checks = @($preflight.checks); services = $status.services; free_disk_gib = $preflight.free_disk_gib; secret_state = $preflight.secret_state; volume_count = @($preflight.volumes).Count }
            $result.details = Protect-AngmooDiagnosticValue -Value ([ordered]@{
                checks = @($checks)
                services = $status.services
                application = $application
                host = $hostDiagnostics
                free_disk_gib = $preflight.free_disk_gib
                secret_state = $preflight.secret_state
                volume_count = @($preflight.volumes).Count
            })
        }
        return [pscustomobject]@{ result = $result; json_requested = $options.json }
    }
    $logArguments = @('logs', '--tail', [string]$options.tail)
    if ($options.follow) { $logArguments += '--follow' }
    $logs = Invoke-AngmooCompose -Project $options.project_name -Contributor $options.contributor -Arguments $logArguments
    $result = New-AngmooLauncherResult -Command $normalizedCommand -Project $options.project_name -Mode $mode -Ok ($logs.exit_code -eq 0) -State $(if ($logs.exit_code -eq 0) { 'observed' } else { 'failed' }) -ExitCode $(if ($logs.exit_code -eq 0) { 0 } else { Get-AngmooExitCode 'preflight_failed' }) -ErrorCode $(if ($logs.exit_code -eq 0) { $null } else { 'compose_config_invalid' }) -Message $(if ($logs.exit_code -eq 0) { 'Compose logs collected.' } else { 'Compose logs could not be read.' }) -Details @{ log_lines = @($logs.output) }
    return [pscustomobject]@{ result = $result; json_requested = $options.json }
    } finally {
        $script:InProcessMode = $false
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
    $applicationProperty = $Result.details.PSObject.Properties['application']
    if ($null -ne $applicationProperty -and $applicationProperty.Value) {
        $application = $applicationProperty.Value
        Write-Output "application=$($application.state)"
    }
    $hostProperty = $Result.details.PSObject.Properties['host']
    if ($null -ne $hostProperty -and $hostProperty.Value) {
        $hostStatus = $hostProperty.Value
        Write-Output "host_free_disk_gib=$($hostStatus.free_disk_gib) docker_storage=$($hostStatus.docker_storage.state)"
    }
    $logsProperty = $Result.details.PSObject.Properties['log_lines']
    if ($null -ne $logsProperty -and $logsProperty.Value) {
        foreach ($line in @($logsProperty.Value)) { Write-Output $line }
    }
}

Export-ModuleMember -Function Invoke-AngmooLauncher, Write-AngmooLauncherHumanResult
