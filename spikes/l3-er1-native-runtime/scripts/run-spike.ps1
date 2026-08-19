[CmdletBinding()]
param(
    [string]$WorkRoot = "",
    [switch]$SkipBundle
)

$ErrorActionPreference = "Stop"
$spikeRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = (Resolve-Path (Join-Path $spikeRoot "..\..")).Path
if (-not $WorkRoot) {
    $WorkRoot = Join-Path $repoRoot ".codex-temp\l3-er1-native-runtime-spike"
}
$pythonRoot = Join-Path $spikeRoot "python"
$tauriRoot = Join-Path $spikeRoot "tauri"
$venv = Join-Path $WorkRoot "py313"
$evidenceRoot = Join-Path $WorkRoot "evidence"
$distRoot = Join-Path $WorkRoot "sidecar-dist"
$buildRoot = Join-Path $WorkRoot "sidecar-build"
$specRoot = Join-Path $WorkRoot "sidecar-spec"
$unicodeDbRoot = Join-Path $WorkRoot "사용자 데이터 공백\그래프"

New-Item -ItemType Directory -Path $WorkRoot,$evidenceRoot,$distRoot,$buildRoot,$specRoot -Force | Out-Null

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required"
}
if (-not (Get-Command rustup -ErrorAction SilentlyContinue)) {
    $cargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
    if (Test-Path -LiteralPath (Join-Path $cargoBin "rustup.exe")) {
        $env:PATH = "$cargoBin;$env:PATH"
    }
}
if (-not (Get-Command rustup -ErrorAction SilentlyContinue)) {
    throw "rustup is required; install the official Rustlang.Rustup package"
}

rustup toolchain install 1.97.1 --profile minimal --component rustfmt --component clippy | Out-Host
uv python install 3.13.12
if ($LASTEXITCODE -ne 0) { throw "Pinned CPython 3.13.12 installation failed" }
uv venv $venv --python 3.13.12 --managed-python --clear
if ($LASTEXITCODE -ne 0) { throw "Pinned CPython 3.13.12 virtual environment creation failed" }
$python = Join-Path $venv "Scripts\python.exe"
uv pip sync --python $python (Join-Path $pythonRoot "requirements.lock")
if ($LASTEXITCODE -ne 0) { throw "Pinned Python dependency installation failed" }

& $python -c "import sys; import ladybug._lbug as native; print(sys.version); print(native.__file__)"
if ($LASTEXITCODE -ne 0) {
    throw "Official LadybugDB PyBind native module import failed on pinned CPython 3.13.12"
}

& $python (Join-Path $pythonRoot "ladybug_probe.py") `
    --database-root $unicodeDbRoot `
    --output (Join-Path $evidenceRoot "ladybug.json")
if ($LASTEXITCODE -ne 0) { throw "LadybugDB compatibility probe failed" }

& $python -m PyInstaller `
    --clean `
    --noconfirm `
    --onefile `
    --name angmoo-spike-sidecar `
    --collect-all ladybug `
    --paths $pythonRoot `
    --distpath $distRoot `
    --workpath $buildRoot `
    --specpath $specRoot `
    (Join-Path $pythonRoot "sidecar.py")
if ($LASTEXITCODE -ne 0) { throw "Sidecar packaging failed" }

& $python (Join-Path $pythonRoot "sidecar_lifecycle_probe.py") `
    --sidecar (Join-Path $distRoot "angmoo-spike-sidecar.exe") `
    --data-root (Join-Path $WorkRoot "sidecar lifecycle 한글 공백") `
    --output (Join-Path $evidenceRoot "sidecar-lifecycle.json")
if ($LASTEXITCODE -ne 0) { throw "Sidecar lifecycle probe failed" }

$hostTriple = (& rustc +1.97.1 --print host-tuple).Trim()
$binaryDir = Join-Path $tauriRoot "src-tauri\binaries"
New-Item -ItemType Directory -Path $binaryDir -Force | Out-Null
$sidecarSource = Join-Path $distRoot "angmoo-spike-sidecar.exe"
$sidecarTarget = Join-Path $binaryDir "angmoo-spike-sidecar-$hostTriple.exe"
Copy-Item -LiteralPath $sidecarSource -Destination $sidecarTarget -Force

Push-Location $tauriRoot
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "Tauri CLI install failed" }
    if ($SkipBundle) {
        npm run tauri -- build --no-bundle
    } else {
        npm run tauri -- build --bundles nsis
    }
    if ($LASTEXITCODE -ne 0) { throw "Tauri build failed" }
} finally {
    Pop-Location
}

$appExe = Join-Path $tauriRoot "src-tauri\target\release\angmoo-native-runtime-spike.exe"
$runtimeEvidence = Join-Path $evidenceRoot "tauri-runtime.json"
$env:ANGMOO_SPIKE_EVIDENCE = $runtimeEvidence
$process = Start-Process -FilePath $appExe -PassThru
if (-not $process.WaitForExit(30000)) {
    Stop-Process -Id $process.Id -Force
    throw "Tauri runtime probe timed out"
}
if (-not (Test-Path -LiteralPath $runtimeEvidence)) {
    throw "Tauri runtime evidence was not created"
}
$runtime = Get-Content -Raw -LiteralPath $runtimeEvidence | ConvertFrom-Json
if ($runtime.status -ne "PASS") {
    throw "Tauri runtime probe failed"
}

$installer = Get-ChildItem -Path (Join-Path $tauriRoot "src-tauri\target\release\bundle\nsis") `
    -Filter "*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
$cargoMetadata = Join-Path $evidenceRoot "cargo-metadata-windows.json"
& cargo +1.97.1 metadata `
    --locked `
    --format-version 1 `
    --filter-platform x86_64-pc-windows-msvc `
    --manifest-path (Join-Path $tauriRoot "src-tauri\Cargo.toml") | Set-Content -Encoding UTF8 -LiteralPath $cargoMetadata
if ($LASTEXITCODE -ne 0) { throw "Cargo metadata generation failed" }
& $python (Join-Path $pythonRoot "generate_spdx_sbom.py") `
    --cargo-metadata $cargoMetadata `
    --package-lock (Join-Path $tauriRoot "package-lock.json") `
    --output (Join-Path $evidenceRoot "native-runtime.spdx.json")
if ($LASTEXITCODE -ne 0) { throw "Native runtime SBOM generation failed" }

$defender = [ordered]@{ available = $false; status = "NOT_RUN"; exit_code = -1 }
if ($installer) {
    $platformRoot = Join-Path $env:ProgramData "Microsoft\Windows Defender\Platform"
    $mpCmdRun = Get-ChildItem -Path $platformRoot -Directory -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending |
        ForEach-Object { Join-Path $_.FullName "MpCmdRun.exe" } |
        Where-Object { Test-Path -LiteralPath $_ } |
        Select-Object -First 1
    if ($mpCmdRun) {
        $defender.available = $true
        & $mpCmdRun -Scan -ScanType 3 -File $installer.FullName -DisableRemediation |
            Set-Content -Encoding UTF8 -LiteralPath (Join-Path $evidenceRoot "defender.txt")
        $defender.exit_code = $LASTEXITCODE
        $defender.status = if ($LASTEXITCODE -eq 0) { "PASS" } else { "FAIL" }
        if ($LASTEXITCODE -ne 0) { throw "Microsoft Defender scan failed" }
    }
}
$summary = [ordered]@{
    schema_version = 1
    status = "PASS"
    production_default_changed = $false
    python = "3.13.12"
    ladybug_version = "0.19.1"
    rust = "1.97.1"
    tauri_cli = "2.11.4"
    sidecar_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $sidecarSource).Hash.ToLowerInvariant()
    sidecar_bytes = (Get-Item -LiteralPath $sidecarSource).Length
    tauri_exe_bytes = (Get-Item -LiteralPath $appExe).Length
    installer_bytes = if ($installer) { $installer.Length } else { 0 }
    defender = $defender
    sbom_path = "native-runtime.spdx.json"
    ladybug_evidence = Get-Content -Raw -LiteralPath (Join-Path $evidenceRoot "ladybug.json") | ConvertFrom-Json
    sidecar_lifecycle = Get-Content -Raw -LiteralPath (Join-Path $evidenceRoot "sidecar-lifecycle.json") | ConvertFrom-Json
    tauri_runtime = $runtime
}
$summary | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $evidenceRoot "summary.json")
$summary | ConvertTo-Json -Depth 8
