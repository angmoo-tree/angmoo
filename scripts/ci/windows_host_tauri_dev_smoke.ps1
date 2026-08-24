Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$preflight = Join-Path $repoRoot 'scripts\dev\desktop-preflight.ps1'
$fixtureRoot = Join-Path ([IO.Path]::GetTempPath()) "angmoo-host-tauri-$([Guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path $fixtureRoot | Out-Null

$base = [ordered]@{
    os = [ordered]@{ is_windows = $true; caption = 'Windows 11'; build = 26200; architecture = 'x86_64' }
    tools = [ordered]@{
        docker_present = $true
        engine_ready = $true
        compose_version = '2.22.0'
        node_version = '22.0.0'
        rust_version = '1.97.1'
        tauri_version = '2.11.4'
        vc_tools = $true
        windows_sdk = '10.0.22621.0'
        webview2 = $true
    }
    docker = [ordered]@{
        services = @('backend', 'frontend')
        stack_state = 'absent'
        port_3000_in_use = $false
    }
    git = [ordered]@{
        repository = $true
        commit = '0123456789abcdef0123456789abcdef01234567'
        branch = 'feat/l3-er7-windows-host-tauri-dev'
        dirty = $false
    }
    processes = [ordered]@{ angmoo_desktop = 0; angmoo_sidecar = 0 }
    environment = [ordered]@{ angmoo_port = $null; forbidden_data_root_variables = @() }
    repository = [ordered]@{
        config_exists = $true
        npm_lock_exists = $true
        cargo_lock_exists = $true
        rust_toolchain_exists = $true
    }
}

function Copy-Fixture {
    return (($base | ConvertTo-Json -Depth 8) | ConvertFrom-Json)
}

function Invoke-Case {
    param(
        [string]$Name,
        [object]$Fixture,
        [int]$ExpectedExit,
        [string]$ExpectedError = ''
    )
    $path = Join-Path $fixtureRoot "$Name.json"
    $Fixture | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $path -Encoding UTF8
    $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $preflight `
        -Json -ProbeFixturePath $path
    $actualExit = $LASTEXITCODE
    if ($actualExit -ne $ExpectedExit) {
        throw "preflight_case_exit_mismatch:$Name expected=$ExpectedExit actual=$actualExit output=$output"
    }
    $payload = $output | ConvertFrom-Json
    if ($ExpectedExit -eq 0 -and $payload.state -ne 'passed') {
        throw "preflight_case_should_pass:$Name"
    }
    if ($ExpectedError -and $ExpectedError -notin @($payload.errors)) {
        throw "preflight_case_missing_error:${Name}:$ExpectedError"
    }
}

try {
    Invoke-Case 'pass-absent-stack' (Copy-Fixture) 0

    $healthy = Copy-Fixture
    $healthy.docker.stack_state = 'healthy'
    $healthy.docker.port_3000_in_use = $true
    Invoke-Case 'pass-reuse-healthy-stack' $healthy 0

    $oldWindows = Copy-Fixture
    $oldWindows.os.build = 19045
    Invoke-Case 'fail-windows-build' $oldWindows 40 'unsupported_windows_build'

    $conflict = Copy-Fixture
    $conflict.docker.port_3000_in_use = $true
    Invoke-Case 'fail-port-conflict' $conflict 40 'frontend_port_conflict'

    $partial = Copy-Fixture
    $partial.docker.stack_state = 'partial-or-unhealthy'
    Invoke-Case 'fail-partial-stack' $partial 40 'docker_stack_partial_or_unhealthy'

    $sidecar = Copy-Fixture
    $sidecar.processes.angmoo_sidecar = 1
    Invoke-Case 'fail-host-sidecar' $sidecar 40 'host_sidecar_process_running'

    $installedData = Copy-Fixture
    $installedData.environment.forbidden_data_root_variables = @('ANGMOO_DATA_ROOT')
    Invoke-Case 'fail-installed-data-override' $installedData 40 'installed_data_root_override_forbidden'

    $customPort = Copy-Fixture
    $customPort.environment.angmoo_port = '3010'
    Invoke-Case 'fail-custom-port' $customPort 40 'frontend_port_must_be_3000'

    $webview = Copy-Fixture
    $webview.tools.webview2 = $false
    Invoke-Case 'fail-webview2' $webview 40 'webview2_missing'

    $vcTools = Copy-Fixture
    $vcTools.tools.vc_tools = $false
    Invoke-Case 'fail-visual-cpp-tools' $vcTools 40 'visual_cpp_tools_missing'

    $windowsSdk = Copy-Fixture
    $windowsSdk.tools.windows_sdk = '10.0.19041.0'
    Invoke-Case 'fail-windows-sdk' $windowsSdk 40 'windows_sdk_unsupported'
} finally {
    Remove-Item -LiteralPath $fixtureRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host 'windows-host-tauri-dev-smoke: PASS cases=11'
exit 0
