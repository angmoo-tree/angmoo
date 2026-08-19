from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
SPIKE = ROOT / "spikes" / "l3-er1-native-runtime"


def test_spike_keeps_production_runtime_unchanged() -> None:
    readme = (SPIKE / "README.md").read_text(encoding="utf-8")
    normalized_readme = " ".join(readme.split())
    assert "does not change Angmoo's production runtime" in normalized_readme
    assert "external provider calls: zero" in readme
    assert "user explicitly" in readme
    assert "CPython `3.13.12`" in readme
    assert "ladybug==0.19.1" in readme
    assert "default PyBind native module" in readme


def test_ladybug_probe_covers_required_native_contracts() -> None:
    source = (SPIKE / "python" / "ladybug_probe.py").read_text(encoding="utf-8")
    for contract in (
        "ExclusiveWriterLock",
        "CREATE NODE TABLE IF NOT EXISTS World",
        "MERGE (source)-[relationship:RELATES_TO]->(target)",
        "RELATES_TO*1..3",
        "world_isolation",
        "serialized_reads",
        "database_reopen",
        "isolated_process_temporary_ascii_drive_alias",
    ):
        assert contract in source


def test_sidecar_uses_loopback_ephemeral_auth_and_parent_watchdog() -> None:
    source = (SPIKE / "python" / "sidecar.py").read_text(encoding="utf-8")
    assert 'listener.bind(("127.0.0.1", 0))' in source
    assert "hmac.compare_digest" in source
    assert "_parent_is_alive" in source
    assert "WindowsAsciiPathAlias" in source
    assert "native_root / graph_path.name" in source
    assert 'docs_url=None' in source
    assert '"/shutdown"' in source
    assert "auth_token" in source


def test_windows_unicode_path_alias_is_ephemeral_and_ascii() -> None:
    source = (SPIKE / "python" / "windows_path_alias.py").read_text(encoding="utf-8")
    assert 'for letter in "ZYXWVUTSRQPONMLKJIHGFED"' in source
    assert '["subst", drive, str(self.target)]' in source
    assert '["subst", drive, "/D"]' in source
    assert "GetLogicalDrives" in source


def test_packaged_sidecar_probe_executes_duplicate_and_orphan_contracts() -> None:
    source = (SPIKE / "python" / "sidecar_lifecycle_probe.py").read_text(encoding="utf-8")
    for contract in (
        "duplicate_writer_blocked",
        "writer_lock_unavailable",
        "unauthenticated_rejected",
        "graceful_shutdown",
        "orphan_cleanup",
        "token_persisted",
    ):
        assert contract in source


def test_tauri_bundles_only_the_pinned_sidecar_contract() -> None:
    config = (SPIKE / "tauri" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8")
    cargo = (SPIKE / "tauri" / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
    rust = (SPIKE / "tauri" / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")
    assert '"externalBin": ["binaries/angmoo-spike-sidecar"]' in config
    assert 'version = "=2.11.5"' in cargo
    assert 'tauri-plugin-shell = "=2.3.5"' in cargo
    assert "Uuid::new_v4" in rust
    assert "unauthenticated_rejected" in rust
    assert "graceful_shutdown_requested" in rust
    assert not re.search(r"(?i)(api[_-]?key|secret)\s*[:=]\s*['\"][^'\"]+", rust)


def test_native_spike_has_windows_reproduction_and_sbom_gates() -> None:
    workflow = (ROOT / ".github" / "workflows" / "native-runtime-spike.yml").read_text(encoding="utf-8")
    runner = (SPIKE / "scripts" / "run-spike.ps1").read_text(encoding="utf-8")
    assert "runs-on: windows-latest" in workflow
    assert "timeout-minutes: 50" in workflow
    assert 'python-version: "3.13.12"' in workflow
    assert "run-spike.ps1" in workflow
    assert "uv python install 3.13.12" in runner
    assert "--python 3.13.12 --managed-python" in runner
    assert "import ladybug._lbug as native" in runner
    assert "generate_spdx_sbom.py" in runner
    assert "MpCmdRun.exe" in runner
    assert "Microsoft Defender scan failed" in runner
