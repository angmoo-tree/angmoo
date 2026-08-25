[CmdletBinding()]
param(
    [switch]$Json,
    [string]$ProbeFixturePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$utf8Support = Join-Path $PSScriptRoot 'windows-host-tauri-utf8.ps1'
. $utf8Support
$utf8Scope = Enter-AngmooUtf8NativeCommandScope

try {

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$contractPath = Join-Path $repoRoot 'desktop\platform\windows-host-tauri-dev.json'
$contract = Get-Content -LiteralPath $contractPath -Raw | ConvertFrom-Json

function ConvertTo-NormalizedVersion {
    param([Parameter(Mandatory = $true)][string]$Value)
    $match = [regex]::Match($Value, '(\d+)\.(\d+)\.(\d+)')
    if (-not $match.Success) { return $null }
    return [version]::new(
        [int]$match.Groups[1].Value,
        [int]$match.Groups[2].Value,
        [int]$match.Groups[3].Value
    )
}

function Get-ActualProbe {
    $windowsHost = $env:OS -eq 'Windows_NT'
    $osBuild = 0
    $osCaption = ''
    if ($windowsHost) {
        $os = Get-CimInstance Win32_OperatingSystem
        $osBuild = [int]$os.BuildNumber
        $osCaption = [string]$os.Caption
    }
    $architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    if ($architecture -eq 'X64') { $architecture = 'x86_64' }

    $dockerPresent = $null -ne (Get-Command docker -ErrorAction SilentlyContinue)
    $engineReady = $false
    $composeVersion = ''
    $composeServices = @()
    $stackState = 'absent'
    if ($dockerPresent) {
        try {
            [void](& docker info --format '{{.ServerVersion}}' 2>$null)
            $engineReady = $LASTEXITCODE -eq 0
        } catch {
            $engineReady = $false
        }
        if ($engineReady) {
            $composeVersion = (& docker compose version --short 2>$null | Select-Object -First 1).Trim()
            $composeArgs = @('-f', 'compose.yml', '-f', 'compose.dev.yml')
            Push-Location $repoRoot
            try {
                $composeServices = @(& docker compose @composeArgs config --services 2>$null)
                $records = @(
                    Invoke-AngmooNativeJsonCommand -CommandType 'compose-ps' -AllowEmpty -JsonLines -Command {
                        & docker compose @composeArgs ps --format json 2>$null
                    }
                )
            } finally {
                Pop-Location
            }
            if ($records.Count -gt 0) {
                $runningHealthy = @(
                    $records | Where-Object {
                        $_.Service -in @('backend', 'frontend') -and
                        $_.State -eq 'running' -and
                        $_.Health -eq 'healthy'
                    }
                )
                $stackState = if ($runningHealthy.Count -eq 2) { 'healthy' } else { 'partial-or-unhealthy' }
            }
        }
    }

    $portInUse = $false
    if ($windowsHost -and (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue)) {
        $portInUse = $null -ne (
            Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue |
                Select-Object -First 1
        )
    }

    $nodeVersion = ''
    if (Get-Command node -ErrorAction SilentlyContinue) {
        $nodeVersion = (& node --version 2>$null | Select-Object -First 1).TrimStart('v')
    }
    $tauriScript = Join-Path $repoRoot 'desktop\node_modules\@tauri-apps\cli\tauri.js'
    $tauriVersion = ''
    if ((Test-Path -LiteralPath $tauriScript -PathType Leaf) -and $nodeVersion) {
        $tauriVersion = (& node $tauriScript --version 2>$null | Select-Object -First 1) -replace '^tauri-cli\s+', ''
    }
    $rustVersion = ''
    $requiredRust = [string]$contract.toolchain.rust_exact
    if (Get-Command rustup -ErrorAction SilentlyContinue) {
        $toolchains = @(& rustup toolchain list 2>$null)
        if ($toolchains -match [regex]::Escape($requiredRust)) {
            $rustVersion = (& rustc "+$requiredRust" --version 2>$null | Select-Object -First 1) -replace '^rustc\s+', ''
            $rustVersion = ($rustVersion -split '\s+')[0]
        }
    }

    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    $vcTools = $false
    if (Test-Path -LiteralPath $vswhere -PathType Leaf) {
        $vcInstall = & $vswhere -latest -products * -requires $contract.toolchain.visual_cpp_component -property installationPath
        $vcTools = -not [string]::IsNullOrWhiteSpace(($vcInstall | Select-Object -First 1))
    }
    $sdkVersions = @(
        Get-ChildItem -LiteralPath 'C:\Program Files (x86)\Windows Kits\10\Lib' -Directory -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty Name
    )
    $sdkVersion = @($sdkVersions | Sort-Object { [version]$_ } -Descending | Select-Object -First 1)
    $sdkVersion = if ($sdkVersion.Count) { [string]$sdkVersion[0] } else { '' }
    $webviewPaths = @(
        'C:\Program Files (x86)\Microsoft\EdgeWebView\Application',
        'C:\Program Files\Microsoft\EdgeWebView\Application'
    )
    $webview2 = $null -ne (
        $webviewPaths | Where-Object {
            Test-Path -LiteralPath $_ -PathType Container
        } | Select-Object -First 1
    )

    $gitRepo = (& git -C $repoRoot rev-parse --is-inside-work-tree 2>$null | Select-Object -First 1) -eq 'true'
    $commit = if ($gitRepo) { (& git -C $repoRoot rev-parse HEAD).Trim() } else { '' }
    $branch = if ($gitRepo) { (& git -C $repoRoot branch --show-current).Trim() } else { '' }
    $dirty = if ($gitRepo) { @(& git -C $repoRoot status --porcelain).Count -gt 0 } else { $true }

    $desktopProcesses = @(Get-Process -Name 'angmoo-desktop' -ErrorAction SilentlyContinue).Count
    $sidecarProcesses = @(Get-Process -Name 'angmoo-sidecar' -ErrorAction SilentlyContinue).Count
    $forbiddenRootVariables = @(
        'ANGMOO_DATA_ROOT',
        'ANGMOO_PRODUCT_DATA_ROOT',
        'ANGMOO_LOCAL_DATA_ROOT',
        'ANGMOO_RUNTIME_ROOT'
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($_)) }

    return [pscustomobject]@{
        os = [pscustomobject]@{
            is_windows = $windowsHost
            caption = $osCaption
            build = $osBuild
            architecture = $architecture
        }
        tools = [pscustomobject]@{
            docker_present = $dockerPresent
            engine_ready = $engineReady
            compose_version = $composeVersion
            node_version = $nodeVersion
            rust_version = $rustVersion
            tauri_version = $tauriVersion
            vc_tools = $vcTools
            windows_sdk = $sdkVersion
            webview2 = $webview2
        }
        docker = [pscustomobject]@{
            services = @($composeServices | Sort-Object)
            stack_state = $stackState
            port_3000_in_use = $portInUse
        }
        git = [pscustomobject]@{
            repository = $gitRepo
            commit = $commit
            branch = $branch
            dirty = $dirty
        }
        processes = [pscustomobject]@{
            angmoo_desktop = $desktopProcesses
            angmoo_sidecar = $sidecarProcesses
        }
        environment = [pscustomobject]@{
            angmoo_port = [Environment]::GetEnvironmentVariable('ANGMOO_PORT')
            forbidden_data_root_variables = @($forbiddenRootVariables)
        }
        repository = [pscustomobject]@{
            config_exists = Test-Path -LiteralPath (Join-Path $repoRoot $contract.host_shell.tauri_config) -PathType Leaf
            npm_lock_exists = Test-Path -LiteralPath (Join-Path $repoRoot 'desktop\package-lock.json') -PathType Leaf
            cargo_lock_exists = Test-Path -LiteralPath (Join-Path $repoRoot 'desktop\src-tauri\Cargo.lock') -PathType Leaf
            rust_toolchain_exists = Test-Path -LiteralPath (Join-Path $repoRoot 'desktop\src-tauri\rust-toolchain.toml') -PathType Leaf
        }
    }
}

function New-Check {
    param(
        [string]$Name,
        [bool]$Ok,
        [string]$Detail,
        [string]$ErrorCode
    )
    return [pscustomobject]@{
        name = $Name
        ok = $Ok
        detail = $Detail
        error_code = if ($Ok) { $null } else { $ErrorCode }
    }
}

$probe = if ($ProbeFixturePath) {
    Get-Content -LiteralPath (Resolve-Path $ProbeFixturePath) -Raw | ConvertFrom-Json
} else {
    Get-ActualProbe
}

$minimumNode = ConvertTo-NormalizedVersion ([string]$contract.toolchain.node_minimum)
$actualNode = ConvertTo-NormalizedVersion ([string]$probe.tools.node_version)
$minimumCompose = ConvertTo-NormalizedVersion ([string]$contract.toolchain.compose_minimum)
$actualCompose = ConvertTo-NormalizedVersion ([string]$probe.tools.compose_version)
$minimumSdk = [version]([string]$contract.toolchain.windows_sdk_minimum)
$actualSdk = ConvertTo-NormalizedVersion ([string]$probe.tools.windows_sdk)
$services = @($probe.docker.services | Sort-Object)
$requiredServices = @($contract.docker.services | Sort-Object)
$serviceMatch = ($services -join ',') -eq ($requiredServices -join ',')
$portValue = [string]$probe.environment.angmoo_port
$portAllowed = [string]::IsNullOrWhiteSpace($portValue) -or $portValue -eq '3000'
$stackAllowed = [string]$probe.docker.stack_state -in @(
    'absent',
    'healthy',
    'partial-or-unhealthy'
)
# A partial Angmoo Compose stack can still own port 3000. desktop-dev.ps1
# deliberately repairs that stack with `up --build` while preserving its
# named volume, so only an unrelated listener with no Angmoo stack is a
# preflight conflict.
$portConflict = [bool]$probe.docker.port_3000_in_use -and $probe.docker.stack_state -eq 'absent'

$checks = @(
    (New-Check 'windows-host' ([bool]$probe.os.is_windows) ([string]$probe.os.caption) 'unsupported_host_os'),
    (New-Check 'windows-build' ([int]$probe.os.build -ge [int]$contract.host.minimum_build) "build=$($probe.os.build)" 'unsupported_windows_build'),
    (New-Check 'architecture' ([string]$probe.os.architecture -in @($contract.host.architectures)) ([string]$probe.os.architecture) 'unsupported_architecture'),
    (New-Check 'docker-cli' ([bool]$probe.tools.docker_present) 'docker' 'docker_cli_missing'),
    (New-Check 'docker-engine' ([bool]$probe.tools.engine_ready) 'engine' 'docker_engine_unavailable'),
    (New-Check 'compose-version' ($null -ne $actualCompose -and $actualCompose -ge $minimumCompose) ([string]$probe.tools.compose_version) 'compose_version_unsupported'),
    (New-Check 'compose-services' $serviceMatch ($services -join ',') 'compose_service_contract_mismatch'),
    (New-Check 'compose-state' $stackAllowed ([string]$probe.docker.stack_state) 'docker_stack_state_unknown'),
    (New-Check 'frontend-port' (-not $portConflict) "in_use=$($probe.docker.port_3000_in_use)" 'frontend_port_conflict'),
    (New-Check 'frontend-port-contract' $portAllowed "ANGMOO_PORT=$portValue" 'frontend_port_must_be_3000'),
    (New-Check 'node-version' ($null -ne $actualNode -and $actualNode -ge $minimumNode) ([string]$probe.tools.node_version) 'node_version_unsupported'),
    (New-Check 'rust-version' ([string]$probe.tools.rust_version -eq [string]$contract.toolchain.rust_exact) ([string]$probe.tools.rust_version) 'rust_toolchain_mismatch'),
    (New-Check 'tauri-cli-version' ([string]$probe.tools.tauri_version -eq [string]$contract.toolchain.tauri_cli_exact) ([string]$probe.tools.tauri_version) 'tauri_cli_mismatch'),
    (New-Check 'visual-cpp-tools' ([bool]$probe.tools.vc_tools) 'MSVC x64' 'visual_cpp_tools_missing'),
    (New-Check 'windows-sdk' ($null -ne $actualSdk -and $actualSdk -ge $minimumSdk) ([string]$probe.tools.windows_sdk) 'windows_sdk_unsupported'),
    (New-Check 'webview2' ([bool]$probe.tools.webview2) 'evergreen' 'webview2_missing'),
    (New-Check 'git-repository' ([bool]$probe.git.repository) ([string]$probe.git.commit) 'git_repository_invalid'),
    (New-Check 'git-commit' ([string]$probe.git.commit -match '^[0-9a-f]{40}$') ([string]$probe.git.commit) 'git_commit_unavailable'),
    (New-Check 'git-branch' (-not [string]::IsNullOrWhiteSpace([string]$probe.git.branch)) ([string]$probe.git.branch) 'git_branch_unavailable'),
    (New-Check 'installed-process' ([int]$probe.processes.angmoo_desktop -eq 0) "count=$($probe.processes.angmoo_desktop)" 'installed_angmoo_process_running'),
    (New-Check 'host-sidecar-process' ([int]$probe.processes.angmoo_sidecar -eq 0) "count=$($probe.processes.angmoo_sidecar)" 'host_sidecar_process_running'),
    (New-Check 'installed-data-env' (@($probe.environment.forbidden_data_root_variables).Count -eq 0) (@($probe.environment.forbidden_data_root_variables) -join ',') 'installed_data_root_override_forbidden'),
    (New-Check 'bridge-config' ([bool]$probe.repository.config_exists) ([string]$contract.host_shell.tauri_config) 'bridge_config_missing'),
    (New-Check 'npm-lock' ([bool]$probe.repository.npm_lock_exists) 'desktop/package-lock.json' 'npm_lock_missing'),
    (New-Check 'cargo-lock' ([bool]$probe.repository.cargo_lock_exists) 'desktop/src-tauri/Cargo.lock' 'cargo_lock_missing'),
    (New-Check 'rust-toolchain-contract' ([bool]$probe.repository.rust_toolchain_exists) 'desktop/src-tauri/rust-toolchain.toml' 'rust_toolchain_contract_missing')
)

$errors = @($checks | Where-Object { -not $_.ok } | ForEach-Object { $_.error_code })
$payload = [ordered]@{
    schema_version = 'angmoo-windows-host-tauri-preflight-v1'
    state = if ($errors.Count -eq 0) { 'passed' } else { 'blocked' }
    contract_id = [string]$contract.contract_id
    commit = [string]$probe.git.commit
    branch = [string]$probe.git.branch
    dirty = [bool]$probe.git.dirty
    docker_stack = [string]$probe.docker.stack_state
    frontend_url = [string]$contract.docker.frontend_url
    checks = $checks
    errors = $errors
}

if ($Json) {
    $payload | ConvertTo-Json -Depth 8 -Compress
} else {
    Write-Host "Angmoo Windows Host Tauri dev preflight: $($payload.state.ToUpperInvariant())"
    Write-Host "  commit: $($payload.commit)"
    Write-Host "  branch: $($payload.branch)"
    Write-Host "  Docker stack: $($payload.docker_stack)"
    foreach ($check in $checks) {
        $marker = if ($check.ok) { 'PASS' } else { 'FAIL' }
        Write-Host "  [$marker] $($check.name): $($check.detail)"
    }
    if ($payload.dirty) {
        Write-Warning 'Working tree has local changes. Docker and Tauri still use this same checkout; record the exact diff before sharing evidence.'
    }
}

$scriptExitCode = if ($errors.Count -gt 0) { 40 } else { 0 }
} finally {
    Exit-AngmooUtf8NativeCommandScope -State $utf8Scope
}
exit $scriptExitCode
