#!/usr/bin/env python3
"""Fail closed when ER6 installer safety or supply-chain contracts drift."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_windows_installer_i18n import validate as validate_installer_i18n  # noqa: E402

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
    _require(bundle["active"] is True, "desktop bundle must be active")
    _require(bundle["targets"] == ["nsis"], "only the NSIS installer is supported")
    _require("wix" not in windows, "retired MSI configuration must not remain active")
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

    hooks = (ROOT / "desktop" / "src-tauri" / "installer-hooks.nsh").read_text(
        encoding="utf-8"
    )
    try:
        validate_installer_i18n(
            config, hooks,
            (ROOT / "desktop/src-tauri/installer-languages.nsh").read_text(encoding="utf-8"),
        )
    except ValueError as error:
        raise SystemExit(f"installer language contract: {error}") from error
    for required in (
        "NSIS_HOOK_PREINSTALL",
        "NSIS_HOOK_PREUNINSTALL",
        "IfSilent angmoo_keep_local_data",
        "$LOCALAPPDATA\\Angmoo\\app",
        "$DeleteAppDataCheckboxState <> 1",
        "Var AngmooFullDeleteConfirmed",
        "StrCpy $AngmooFullDeleteConfirmed 0",
        "StrCpy $AngmooFullDeleteConfirmed 1",
        "${If} $AngmooFullDeleteConfirmed = 1",
        "ANGMOO_VERIFY_NOT_REPARSE",
        "$LOCALAPPDATA\\com.angmoo.desktop",
        "$LOCALAPPDATA\\Angmoo.__casefix__",
        'SetOutPath "$TEMP"',
        'Rename "$LOCALAPPDATA\\angmoo" "$LOCALAPPDATA\\Angmoo.__casefix__"',
        'Rename "$LOCALAPPDATA\\Angmoo.__casefix__" "$LOCALAPPDATA\\Angmoo"',
        "installer-preflight.ps1",
        "$LOCALAPPDATA\\Angmoo\\app.__install_staging__",
        "verify-installed-payload.ps1",
        "installer-payload-transaction.ps1",
        "--installer-data-preflight",
        "--installer-data-upgrade",
        "--installer-result-path",
        "-Action RestoreFailure",
        "installer_staging_digest_mismatch",
        "installer_embedded_data_migration_failed",
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
    _require(
        "${If} $DeleteAppDataCheckboxState = 1" not in hooks,
        "post-uninstall cleanup must not treat a checked box as confirmation",
    )
    confirmation = hooks.index("StrCpy $AngmooFullDeleteConfirmed 1")
    final_warning = hooks.index('"$(AngmooConfirmFullDelete)"')
    final_validation = hooks.index(
        '!insertmacro ANGMOO_VERIFY_NOT_REPARSE "$LOCALAPPDATA\\com.angmoo.desktop" angmoo_legacy'
    )
    first_recursive_delete = hooks.index(
        'RMDir /r "$LOCALAPPDATA\\Angmoo\\canonical"'
    )
    _require(
        final_warning < final_validation < confirmation < first_recursive_delete,
        "full-delete confirmation must follow final Yes and all validations",
    )
    post_uninstall = hooks.split("!macro NSIS_HOOK_POSTUNINSTALL", 1)[1]
    _require(
        "$DeleteAppDataCheckboxState" not in post_uninstall,
        "post-uninstall must be guarded only by confirmed full deletion",
    )

    workflow = (ROOT / ".github" / "workflows" / "windows-installer.yml").read_text(
        encoding="utf-8"
    )
    qualification = (ROOT / 'scripts/ci/run_windows_postgresql_qualification.py').read_text(encoding='utf-8')
    scan = (ROOT / 'scripts/ci/run_windows_postgresql_qualification.ps1').read_text(encoding='utf-8')
    for required in ('build:installer','build_desktop_release_metadata.py','angmoo-installer.spdx.json',
        'angmoo-installer.provenance.json','THIRD_PARTY_NOTICES.md','release-candidate-backup.json',
        'check_windows_gui_subsystems.py','check_er6_desktop_supply_chain.py','run_er6_defender_trigger_matrix.ps1',
        'er6-defender-trigger-matrix.json','name: windows-installer-build','name: windows-installer-clean-install',
        'windows-installer-supported-upgrade','windows-installer-failure-recovery','windows_installer_required_matrix_pass',
        'windows_postgresql_coverage.py','run_windows_postgresql_qualification.ps1'):
        _require(required in workflow, f'installer workflow contract missing: {required}')
    for required in ('OLD_EXE_SHA','windows_pg_hosted_only','windows_pg_existing_installation_refused',
        'LOCAL_POSTGRESQL','--migrate-sqlite','interrupted_after_canonical','windows_pg_source_changed_after_conversion',
        'windows_pg_silent_uninstall_deleted_data','windows_pg_actual_host_cleanup_failed'):
        _require(required in qualification, f'PostgreSQL qualification missing: {required}')
    for required in ('Get-MpThreat','Get-MpThreatDetection','installed_postrun_scan','Start-MpScan',
        'Get-FileHash','interactive_full_delete=','user_gate_required'):
        _require(required in scan, f'installer security qualification missing: {required}')

    sidecar_build = (ROOT / "desktop" / "scripts" / "build-sidecar.ps1").read_text(
        encoding="utf-8"
    )
    _require("--noconsole" in sidecar_build, "packaged sidecar console must be hidden")
    _require("--noupx" in sidecar_build, "packaged sidecar must explicitly disable UPX")
    _require('ValidateSet("OneFile", "OneDir")' in sidecar_build, "sidecar layout comparison is missing")
    for required in (
        "sqlite_versions/manifests",
        "ladybug_versions/manifests",
        "--add-data $sqliteManifestData",
        "--add-data $ladybugManifestData",
        '$sqliteDeltaRoot = Join-Path $backendRoot "app/runtime/migrations/sqlite_versions"',
        "$sqliteDeltaRoot/*.json;app/runtime/migrations/sqlite_versions",
        "--add-data $sqliteDeltaData",
    ):
        _require(
            required in sidecar_build.replace("\\", "/"),
            f"packaged embedded migration manifest missing: {required}",
        )
    _require("--exclude-module psycopg" not in sidecar_build, "PostgreSQL driver cannot be excluded from the official sidecar")
    for marker in ('--collect-all psycopg','--collect-all psycopg_binary','--hidden-import sqlalchemy.dialects.postgresql.psycopg','build_windows_postgresql.py'):
        _require(marker in sidecar_build, 'required PostgreSQL sidecar resource missing: '+marker)
    _require(bundle['resources'].get('resources/postgresql/')=='postgresql/', 'native PostgreSQL resource directory must be bundled')

    defender_matrix = (
        ROOT / "scripts" / "ci" / "run_er6_defender_trigger_matrix.ps1"
    ).read_text(encoding="utf-8")
    for required in (
        "real sidecar did not publish its runtime endpoint",
        "installed runtime did not publish its endpoint",
    ):
        _require(
            required in defender_matrix,
            f"Defender matrix runtime readiness contract missing: {required}",
        )

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
        "desktop_sidecar_schema_unsupported",
        "desktop_sidecar_data_migration_failed",
    ):
        _require(required in launcher, f"no-console readiness contract missing: {required}")

    desktop_package = json.loads(
        (ROOT / "desktop" / "package.json").read_text(encoding="utf-8")
    )
    installer_command = desktop_package["scripts"]["build:installer"]
    _require(
        installer_command == "npm run build:sidecar && tauri build --bundles nsis",
        "installer build must run the reviewed Tauri bundle path",
    )
    for marker in (
        "!system",
        "prepare-installer-payload.ps1",
        "MAINBINARYSRCPATH",
        "-SkipHostBuild",
        "-HostPath",
        "-SidecarPath",
        "-ManifestPath",
    ):
        _require(
            marker in hooks,
            f"NSIS must freeze the final host and sidecar digests: {marker}",
        )
    for script_name in (
        "prepare-installer-payload.ps1",
        "installer-preflight.ps1",
        "verify-installed-payload.ps1",
        "test-installer-payload-verifier.ps1",
        "installer-payload-transaction.ps1",
        "test-installer-payload-transaction.ps1",
    ):
        _require(
            (ROOT / "desktop" / "scripts" / script_name).is_file(),
            f"installer payload script missing: {script_name}",
        )
    for relative in (
        "scripts/ci/check_windows_installer_supported_upgrade_matrix.py",
        "scripts/ci/build_windows_installer_supported_upgrade_fixture.py",
        "scripts/ci/run_windows_installer_supported_upgrade.ps1",
        "scripts/ci/verify_windows_installer_supported_upgrade_fixture.py",
    ):
        _require(
            (ROOT / relative).is_file(),
            f"supported predecessor installer Gate missing: {relative}",
        )
    transaction = (
        ROOT / "desktop" / "scripts" / "installer-payload-transaction.ps1"
    ).read_text(encoding="utf-8")
    for required in (
        "Read-InstallerFailureResult",
        "Assert-RollbackDataCompatibility",
        "installer_previous_payload_restored",
        "installer_active_data_generation_changed",
    ):
        _require(
            required in transaction,
            f"installer rollback contract missing: {required}",
        )
    verifier = (
        ROOT / "desktop" / "scripts" / "verify-installed-payload.ps1"
    ).read_text(encoding="utf-8")
    _require(
        "installer_payload_digest_parity_pass" in verifier,
        "installed payload verifier must emit the stable parity success code",
    )
    print("desktop-installer-contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
