#!/usr/bin/env python3
"""Fail closed when ER6 installer safety or supply-chain contracts drift."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> int:
    config = json.loads(
        (ROOT / "desktop" / "src-tauri" / "tauri.conf.json").read_text(
            encoding="utf-8"
        )
    )
    bundle = config["bundle"]
    windows = bundle["windows"]
    nsis = windows["nsis"]
    wix = windows["wix"]
    _require(bundle["active"] is True, "desktop bundle must be active")
    _require(set(bundle["targets"]) == {"nsis", "msi"}, "NSIS and MSI required")
    _require(bundle["license"] == "GPL-3.0-only", "GPL license metadata missing")
    _require(
        bundle["resources"]["../../THIRD_PARTY_NOTICES.md"]
        == "THIRD_PARTY_NOTICES.md",
        "third-party notice is not bundled",
    )
    _require(
        windows["webviewInstallMode"]["type"] == "offlineInstaller",
        "offline WebView2 installer is required",
    )
    _require(windows["allowDowngrades"] is False, "installer downgrade must fail")
    _require(nsis["installMode"] == "currentUser", "per-user install is required")
    _require(nsis["installerHooks"] == "installer-hooks.nsh", "hooks missing")
    _require(bool(wix["upgradeCode"]), "stable MSI upgrade code missing")
    _require(
        wix["template"] == "wix/product-main.wxs",
        "the reviewed per-user WiX template is required",
    )

    hooks = (ROOT / "desktop" / "src-tauri" / "installer-hooks.nsh").read_text(
        encoding="utf-8"
    )
    for required in (
        "NSIS_HOOK_PREINSTALL",
        "NSIS_HOOK_PREUNINSTALL",
        "IfSilent angmoo_keep_local_data",
        "$LOCALAPPDATA\\Angmoo\\app",
        "$DeleteAppDataCheckboxState <> 1",
        "Permanently delete every Angmoo World",
        "ANGMOO_VERIFY_NOT_REPARSE",
        "$LOCALAPPDATA\\com.angmoo.desktop",
    ):
        _require(required in hooks, f"uninstall safety contract missing: {required}")
    for required in (
        "$LOCALAPPDATA\\Angmoo\\canonical",
        "$LOCALAPPDATA\\Angmoo\\graph",
        "$LOCALAPPDATA\\Angmoo\\search",
        "$LOCALAPPDATA\\Angmoo\\media",
        "$LOCALAPPDATA\\Angmoo\\secrets",
        "$LOCALAPPDATA\\Angmoo\\runtime",
        "$LOCALAPPDATA\\Angmoo\\logs",
        "$LOCALAPPDATA\\Angmoo\\webview",
    ):
        _require(required in hooks, f"owned data child missing: {required}")
    _require(
        'RMDir /r "$LOCALAPPDATA\\Angmoo"' not in hooks,
        "the whole product namespace must never be recursively deleted",
    )

    wix_template = (
        ROOT / "desktop" / "src-tauri" / "wix" / "product-main.wxs"
    ).read_text(encoding="utf-8")
    for required in (
        'InstallScope="perUser"',
        'Directory Id="$(var.PlatformProgramFilesFolder)"',
        'Directory Id="INSTALLDIR" Name="Angmoo"',
        'Id="INSTALLDIR"',
        'Value="[LocalAppDataFolder]Angmoo\\app"',
        'Before="CostFinalize"',
        'Sequence="both"',
    ):
        _require(required in wix_template, f"WiX app-root contract missing: {required}")
    for forbidden in ('InstallScope="perMachine"',):
        _require(forbidden not in wix_template, f"machine-wide WiX path forbidden: {forbidden}")

    workflow = (ROOT / ".github" / "workflows" / "windows-installer.yml").read_text(
        encoding="utf-8"
    )
    for required in (
        "build:installer",
        "build_desktop_release_metadata.py",
        "angmoo-installer.spdx.json",
        "angmoo-installer.provenance.json",
        "THIRD_PARTY_NOTICES.md",
        "release-candidate-backup.json",
        "angmoo-desktop.exe",
        "runtime\\sidecar.endpoint.json",
        "check_windows_gui_subsystems.py",
        "Get-MpThreat",
        "installed_prelaunch_scan",
        "installed_postrun_scan",
        "angmoo-sidecar.exe",
        "angmoo-windows-defender-evidence",
        "check_er6_desktop_supply_chain.py",
        "run_er6_defender_trigger_matrix.ps1",
        "er6-defender-trigger-matrix.json",
        "Get-MpThreatDetection",
        "NoNewDefenderDetection",
    ):
        _require(required in workflow, f"installer workflow contract missing: {required}")

    sidecar_build = (ROOT / "desktop" / "scripts" / "build-sidecar.ps1").read_text(
        encoding="utf-8"
    )
    _require("--noconsole" in sidecar_build, "packaged sidecar console must be hidden")
    _require("--noupx" in sidecar_build, "packaged sidecar must explicitly disable UPX")
    _require('ValidateSet("OneFile", "OneDir")' in sidecar_build, "sidecar layout comparison is missing")
    _require("--exclude-module psycopg" in sidecar_build, "legacy PostgreSQL driver must be excluded from product sidecar")
    _require("--hidden-import psycopg" not in sidecar_build, "legacy PostgreSQL driver must not be a hidden import")

    cargo_manifest = (ROOT / "desktop" / "src-tauri" / "Cargo.toml").read_text(
        encoding="utf-8"
    )
    for required in (
        "[package.metadata.tauri-winres]",
        'OriginalFilename = "angmoo-desktop.exe"',
        'InternalName = "Angmoo"',
        "LegalCopyright",
    ):
        _require(required in cargo_manifest, f"Windows product metadata missing: {required}")
    tauri_main = (ROOT / "desktop" / "src-tauri" / "src" / "main.rs").read_text(
        encoding="utf-8"
    )
    _require(
        'cfg_attr(not(debug_assertions), windows_subsystem = "windows")'
        in tauri_main,
        "packaged Tauri host console must be hidden",
    )
    launcher = (
        ROOT / "desktop" / "src-tauri" / "src" / "desktop_runtime.rs"
    ).read_text(encoding="utf-8")
    for required in (
        "ProductDataPaths::resolve",
        '"--data-root"',
        "sidecar.endpoint.json",
        "logical_sidecar_pid",
        "dynamic_port",
        "expected_generation",
        'http_request(ready.dynamic_port, "GET", "/health", &token)',
    ):
        _require(required in launcher, f"no-console readiness contract missing: {required}")
    print("desktop-installer-contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
