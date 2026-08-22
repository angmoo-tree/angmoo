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

    hooks = (ROOT / "desktop" / "src-tauri" / "installer-hooks.nsh").read_text(
        encoding="utf-8"
    )
    for required in (
        "NSIS_HOOK_PREUNINSTALL",
        "IfSilent angmoo_keep_local_data",
        "$LOCALAPPDATA\\com.angmoo.desktop",
    ):
        _require(required in hooks, f"uninstall safety contract missing: {required}")

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
    ):
        _require(required in workflow, f"installer workflow contract missing: {required}")
    print("desktop-installer-contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
