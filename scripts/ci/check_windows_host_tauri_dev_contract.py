#!/usr/bin/env python3
"""Fail closed when the Windows Host Tauri dev bridge contract drifts."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def check_repo(*, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        contract = json.loads(
            _read(root, "desktop/platform/windows-host-tauri-dev.json")
        )
        tauri_config = json.loads(
            _read(root, "desktop/src-tauri/tauri.contributor-docker.conf.json")
        )
        package = json.loads(_read(root, "desktop/package.json"))
        cargo = _read(root, "desktop/src-tauri/Cargo.toml")
        launch_mode = _read(root, "desktop/src-tauri/src/launch_mode.rs")
        runtime = _read(root, "desktop/src-tauri/src/desktop_runtime.rs")
        host = _read(root, "desktop/src-tauri/src/lib.rs")
        paths = _read(root, "desktop/src-tauri/src/product_paths.rs")
        preflight = _read(root, "scripts/dev/desktop-preflight.ps1")
        launcher = _read(root, "scripts/dev/desktop-dev.ps1")
        utf8_support = _read(root, "scripts/dev/windows-host-tauri-utf8.ps1")
        smoke = _read(root, "scripts/ci/windows_host_tauri_dev_smoke.ps1")
        utf8_smoke = _read(root, "scripts/ci/windows_host_tauri_utf8_smoke.ps1")
        codeowners = _read(root, ".github/CODEOWNERS")
        workflow = _read(root, ".github/workflows/windows-host-tauri-dev.yml")
        architecture = _read(
            root, "docs/architecture/l3-er7-windows-host-tauri-dev.md"
        )
        public = _read(root, "docs/public/windows-host-tauri-dev.md")
        readme = _read(root, "README.md")
        contributing = _read(root, "CONTRIBUTING.md")
    except (OSError, json.JSONDecodeError) as exc:
        return [f"windows host Tauri dev contract cannot be read: {exc}"]

    if contract.get("contract_id") != "angmoo-windows-host-tauri-dev-v1":
        errors.append("host Tauri support contract id mismatch")
    if contract.get("runtime_mode") != "contributor-docker-bridge":
        errors.append("host Tauri runtime mode mismatch")
    if contract.get("host", {}).get("minimum_build") != 22000:
        errors.append("Windows 11 minimum build must be explicit")
    if contract.get("host", {}).get("architectures") != ["x86_64"]:
        errors.append("only the verified Windows x64 host may pass preflight")
    docker = contract.get("docker", {})
    if docker.get("services") != ["backend", "frontend"]:
        errors.append("bridge must reuse exactly backend and frontend")
    if docker.get("backend_profile") != "CONTRIBUTOR_EMBEDDED":
        errors.append("bridge must reuse CONTRIBUTOR_EMBEDDED")
    for key, expected in (
        ("persistence", "sqlite"),
        ("graph", "ladybug"),
        ("scheduler", "in-process"),
        ("projector", "in-process"),
    ):
        if docker.get(key) != expected:
            errors.append(f"Docker bridge {key} mismatch")
    lifecycle = contract.get("lifecycle", {})
    for key in (
        "preserve_docker_stack_on_exit",
        "preserve_named_volume_on_exit",
    ):
        if lifecycle.get(key) is not True:
            errors.append(f"bridge lifecycle must preserve {key}")
    for key in ("spawn_host_sidecar", "read_or_write_installed_product_data"):
        if lifecycle.get(key) is not False:
            errors.append(f"bridge lifecycle must forbid {key}")

    build = tauri_config.get("build", {})
    if build.get("beforeDevCommand", "missing") is not None:
        errors.append("bridge must not start a host frontend dev server")
    if build.get("devUrl") != "http://127.0.0.1:3000":
        errors.append("bridge must load the Docker frontend origin")
    if tauri_config.get("bundle", {}).get("active") is not False:
        errors.append("bridge configuration must never build a bundle")
    if tauri_config.get("bundle", {}).get("externalBin") != []:
        errors.append("bridge configuration must not package a sidecar")
    capabilities = (
        tauri_config.get("app", {}).get("security", {}).get("capabilities", [])
    )
    if len(capabilities) != 1:
        errors.append("bridge must expose one narrow remote capability")
    else:
        capability = capabilities[0]
        if set(capability.get("windows", [])) != {
            "main",
            "studio",
            "relationship-graph",
        }:
            errors.append("bridge window label boundary mismatch")
        if capability.get("remote", {}).get("urls") != [
            "http://127.0.0.1:3000/*"
        ]:
            errors.append("bridge remote origin allowlist mismatch")

    expected_script = (
        "tauri dev --config src-tauri/tauri.contributor-docker.conf.json "
        "--features contributor-docker-bridge"
    )
    if package.get("scripts", {}).get("dev:docker-bridge") != expected_script:
        errors.append("desktop Docker bridge command mismatch")
    for marker in (
        "[features]",
        "contributor-docker-bridge = []",
    ):
        if marker not in cargo:
            errors.append(f"Cargo bridge feature missing: {marker}")
    for marker in (
        'cfg(feature = "contributor-docker-bridge")',
        "contributor_docker_bridge_release_forbidden",
        "ContributorDockerBridge",
    ):
        if marker not in launch_mode:
            errors.append(f"typed launch mode guard missing: {marker}")
    for marker in (
        "activate_contributor_bridge",
        'runtime_mode: "contributor-docker-bridge"',
        "contributor_bridge_host_sidecar_forbidden",
        "assert!(runtime.child.is_none())",
        "assert!(runtime.runtime_root.is_none())",
    ):
        if marker not in runtime:
            errors.append(f"sidecar exclusion contract missing: {marker}")
    for marker in (
        "prepare_contributor_bridge_directory",
        "desktop_runtime::activate_contributor_bridge",
    ):
        if marker not in host and marker not in paths:
            errors.append(f"bridge bootstrap contract missing: {marker}")
    if "prepare_runtime_owned_directories()?;" not in host:
        errors.append("installed product bootstrap must remain available")

    for marker in (
        "unsupported_windows_build",
        "partial-or-unhealthy",
        "docker_stack_state_unknown",
        "frontend_port_conflict",
        "host_sidecar_process_running",
        "installed_data_root_override_forbidden",
        "visual_cpp_tools_missing",
        "windows_sdk_unsupported",
        "webview2_missing",
    ):
        if marker not in preflight or marker not in smoke:
            errors.append(f"preflight fail-closed case missing: {marker}")
    for marker in (
        "pass-repair-owned-partial-stack",
        "pass-repair-owned-partial-stack-with-port",
    ):
        if marker not in smoke:
            errors.append(f"recoverable stack case missing: {marker}")
    for marker in (
        "Get-ProtectedDataFingerprint",
        "contributor_bridge_spawned_host_sidecar",
        "installed_product_data_changed_during_contributor_bridge",
        "docker compose @composeFiles up -d --build --wait",
        "npm.cmd --prefix",
        "dev:docker-bridge",
        "preserved",
    ):
        if marker not in launcher:
            errors.append(f"one-command lifecycle guard missing: {marker}")
    for marker in (
        "Enter-AngmooUtf8NativeCommandScope",
        "Exit-AngmooUtf8NativeCommandScope",
        "Invoke-AngmooNativeJsonCommand",
        "compose_json_decode_failed",
        "MaximumAttempts = 2",
        "chars=$CharacterLength",
        "bytes=$ByteLength",
        "reason=$Reason",
    ):
        if marker not in utf8_support:
            errors.append(f"UTF-8 native command contract missing: {marker}")
    for script_name, script in (("preflight", preflight), ("launcher", launcher)):
        for marker in (
            "windows-host-tauri-utf8.ps1",
            "Enter-AngmooUtf8NativeCommandScope",
            "Exit-AngmooUtf8NativeCommandScope",
            "finally",
        ):
            if marker not in script:
                errors.append(f"{script_name} UTF-8 scope missing: {marker}")
    for marker in (
        "windows-powershell-5.1",
        "powershell-7",
        "code_page = 949",
        "code_page = 65001",
        "utf8_retry_bound_mismatch",
        "utf8_failure_leaked_raw_json",
        "utf8_pipeline_scope_not_restored",
    ):
        if marker not in utf8_smoke:
            errors.append(f"UTF-8 Windows regression case missing: {marker}")
    for forbidden in (
        "docker compose down",
        "--volumes",
        "volume prune",
        "Remove-Item -LiteralPath $protectedDataRoot",
    ):
        if forbidden.lower() in launcher.lower():
            errors.append(f"destructive bridge lifecycle found: {forbidden}")

    for protected in (
        "/desktop/src-tauri/",
        "/desktop/platform/",
        "/scripts/dev/desktop-preflight.ps1",
        "/scripts/dev/desktop-dev.ps1",
        "/scripts/dev/windows-host-tauri-utf8.ps1",
        "/scripts/ci/windows_host_tauri_utf8_smoke.ps1",
        "@jingujeon",
    ):
        if protected not in codeowners:
            errors.append(f"platform-shell review boundary missing: {protected}")
    for marker in (
        "windows_host_tauri_dev_smoke.ps1",
        "windows_host_tauri_utf8_smoke.ps1",
        "contributor-docker-bridge",
        "check_windows_host_tauri_dev_contract.py",
        "tauri.contributor-docker.conf.json",
        "--no-bundle",
    ):
        if marker not in workflow:
            errors.append(f"Hosted Windows workflow contract missing: {marker}")
    for marker in (
        "Docker contributor stack",
        "Host Tauri",
        "%LOCALAPPDATA%\\Angmoo",
        "main",
        "studio",
        "relationship-graph",
    ):
        if marker not in architecture:
            errors.append(f"architecture evidence missing: {marker}")
    for marker in (
        ".\\scripts\\dev\\desktop-preflight.ps1",
        ".\\scripts\\dev\\desktop-dev.ps1",
        "Windows 11 x64",
        "Docker",
        "installed-user data",
    ):
        if marker not in public:
            errors.append(f"public bridge guide missing: {marker}")
    for marker in (
        "Docker Browser Run",
        "Docker contributor development",
        "Windows Host Tauri dev",
        "Windows installer",
    ):
        if marker not in readme:
            errors.append(f"README execution-path map missing: {marker}")
    if "platform-shell maintainer review" not in contributing.lower():
        errors.append("CONTRIBUTING platform-shell review Gate missing")
    return errors


def main() -> int:
    errors = check_repo()
    if errors:
        for error in errors:
            print(f"windows-host-tauri-dev-contract: FAIL: {error}")
        return 1
    print("windows-host-tauri-dev-contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
