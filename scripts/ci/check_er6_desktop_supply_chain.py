#!/usr/bin/env python3
"""Fail closed when the installed ER6 desktop trust boundary drifts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _locked_versions() -> dict[str, Any]:
    package_lock = json.loads(
        (ROOT / "desktop" / "package-lock.json").read_text(encoding="utf-8")
    )
    cargo_lock = (ROOT / "desktop" / "src-tauri" / "Cargo.lock").read_text(
        encoding="utf-8"
    )
    pnpm_lock = (ROOT / "frontend" / "pnpm-lock.yaml").read_text(encoding="utf-8")
    sidecar_build = (
        ROOT / "desktop" / "scripts" / "build-sidecar.ps1"
    ).read_text(encoding="utf-8")
    return {
        "tauri_cli": package_lock["packages"]["node_modules/@tauri-apps/cli"][
            "version"
        ],
        "tauri_rust": re.search(
            r'name = "tauri"\s+version = "([^"]+)"', cargo_lock
        ).group(1),
        "pyinstaller": re.search(
            r"PyInstaller; assert PyInstaller\.__version__ == '([^']+)'",
            sidecar_build,
        ).group(1),
        "pnpm_lock_version": re.search(r"lockfileVersion: '([^']+)'", pnpm_lock).group(
            1
        ),
    }


def _git_output(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


def _is_reviewed_local_url(candidate: str) -> bool:
    parsed = urlsplit(candidate.replace("{port}", "1"))
    if parsed.scheme != "http" or parsed.username or parsed.password:
        return False
    if parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        return False
    if parsed.hostname == "tauri.localhost":
        return parsed.port is None
    if parsed.hostname == "127.0.0.1":
        return parsed.port is not None
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--base-ref", default="")
    args = parser.parse_args()

    config = json.loads(
        (ROOT / "desktop" / "src-tauri" / "tauri.conf.json").read_text(
            encoding="utf-8"
        )
    )
    capability = json.loads(
        (
            ROOT
            / "desktop"
            / "src-tauri"
            / "capabilities"
            / "product-shell.json"
        ).read_text(encoding="utf-8")
    )
    hooks_path = ROOT / "desktop" / "src-tauri" / "installer-hooks.nsh"
    hooks = hooks_path.read_text(encoding="utf-8")
    launcher = (
        ROOT / "desktop" / "src-tauri" / "src" / "desktop_runtime.rs"
    ).read_text(encoding="utf-8")
    sidecar = (
        ROOT / "backend" / "app" / "runtime" / "desktop_sidecar.py"
    ).read_text(encoding="utf-8")
    cargo = (ROOT / "desktop" / "src-tauri" / "Cargo.toml").read_text(
        encoding="utf-8"
    )
    build_script = (
        ROOT / "desktop" / "scripts" / "build-sidecar.ps1"
    ).read_text(encoding="utf-8")

    _require(
        config["bundle"]["externalBin"] == ["binaries/angmoo-sidecar"],
        "only the pinned Angmoo sidecar may be bundled",
    )
    _require(
        capability["permissions"] == ["core:default"],
        "frontend capability must not expose shell or process permissions",
    )
    _require(
        set(capability["windows"]) == {"main", "studio", "relationship-graph"},
        "desktop capability window scope drifted",
    )
    _require(
        'tauri-plugin-shell = "=2.3.5"' in cargo,
        "the reviewed shell implementation must stay exactly pinned",
    )
    for required in (
        '.sidecar("angmoo-sidecar")',
        '"--parent-pid"',
        '"--data-root"',
        '"--legacy-data-root"',
        '"--runtime-root"',
        '"--launch-id"',
        '"DESKTOP_LAUNCH_TOKEN"',
        '"DESKTOP_ALLOWED_ORIGIN"',
    ):
        _require(required in launcher, f"reviewed sidecar launch contract missing: {required}")
    for forbidden in (
        "powershell",
        "cmd.exe",
        "0.0.0.0",
        "download",
        "autostart",
    ):
        _require(
            forbidden not in launcher.lower(),
            f"unexpected launcher capability or network behavior: {forbidden}",
        )
    launcher_urls = re.findall(r"https?://[^\"'\s]+", launcher)
    _require(
        all(_is_reviewed_local_url(url) for url in launcher_urls),
        f"desktop launcher contains a non-local URL: {launcher_urls}",
    )
    _require(
        'listener.bind(("127.0.0.1", 0))' in sidecar,
        "desktop sidecar must bind only to an ephemeral loopback port",
    )
    _require(
        'host="127.0.0.1"' in sidecar,
        "uvicorn desktop host must remain loopback-only",
    )
    _require(
        "--noconsole" in build_script and "--noupx" in build_script,
        "sidecar must remain no-console and explicitly unpacked",
    )
    _require(
        "--runtime-tmpdir" not in build_script,
        "sidecar must not force a hidden extraction directory",
    )
    recursive_deletes = [
        line.strip() for line in hooks.splitlines() if re.search(r"\bRMDir\s+/r\b", line)
    ]
    _require(
        recursive_deletes == ['RMDir /r "$LOCALAPPDATA\\com.angmoo.desktop"'],
        "uninstaller recursive deletion escaped the one approved app-data root",
    )
    combined_desktop_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "desktop" / "src-tauri" / "src").glob("*.rs"))
    ).lower()
    for forbidden in (
        "currentversion\\run",
        "startupapproved",
        "tauri_plugin_autostart",
        "schtasks",
        "invoke-webrequest",
    ):
        _require(
            forbidden not in combined_desktop_sources.lower() + hooks.lower(),
            f"unexpected persistence or downloader behavior: {forbidden}",
        )

    evidence: dict[str, Any] = {
        "schema_version": 1,
        "status": "PASS",
        "commit": _git_output("rev-parse", "HEAD"),
        "locks": {
            str(path.relative_to(ROOT)).replace("\\", "/"): _sha256(path)
            for path in (
                ROOT / "backend" / "uv.lock",
                ROOT / "frontend" / "pnpm-lock.yaml",
                ROOT / "desktop" / "package-lock.json",
                ROOT / "desktop" / "src-tauri" / "Cargo.lock",
            )
        },
        "locked_versions": _locked_versions(),
        "trust_boundary": {
            "frontend_permissions": capability["permissions"],
            "external_binaries": config["bundle"]["externalBin"],
            "sidecar_bind": "127.0.0.1:ephemeral",
            "sidecar_arguments": [
                "parent-pid",
                "data-root",
                "legacy-data-root",
                "runtime-root",
                "launch-id",
            ],
            "recursive_delete_roots": ["LOCALAPPDATA/com.angmoo.desktop"],
            "autostart_registration": False,
            "runtime_download_or_self_update": False,
        },
    }
    if args.base_ref:
        evidence["dependency_lock_diff"] = _git_output(
            "diff",
            "--name-status",
            f"{args.base_ref}...HEAD",
            "--",
            "backend/uv.lock",
            "frontend/pnpm-lock.yaml",
            "desktop/package-lock.json",
            "desktop/src-tauri/Cargo.lock",
        ).splitlines()
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print("er6-desktop-supply-chain: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
