from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "backend" / "app"


def test_l4_social_runtime_has_one_concrete_owner_and_no_temporary_facades() -> None:
    required = (
        APP_ROOT / "domains" / "social" / "contracts" / "__init__.py",
        APP_ROOT / "domains" / "social" / "contracts" / "inbox.py",
        APP_ROOT / "domains" / "social" / "models" / "manual_writes.py",
        APP_ROOT / "runtime" / "social" / "sqlalchemy_unit_of_work.py",
        APP_ROOT / "domains" / "social" / "service" / "manual_inbox.py",
        APP_ROOT / "runtime" / "social" / "sqlalchemy_read_repository.py",
        APP_ROOT / "runtime" / "routine_posts" / "sqlalchemy_runtime.py",
        APP_ROOT / "core" / "sqlite_concurrency.py",
    )
    removed_packages = (
        APP_ROOT / "compatibility" / "manual_social",
        APP_ROOT / "domains" / "manual_social",
    )
    removed_files = (
        APP_ROOT
        / "domains"
        / "routine_posts"
        / "infrastructure"
        / "sqlalchemy_runtime.py",
        APP_ROOT / "runtime" / "persistence" / "sqlite_concurrency.py",
    )

    assert all(path.is_file() for path in required)
    assert all(not any(path.rglob("*.py")) for path in removed_packages)
    assert all(not path.exists() for path in removed_files)


def test_l4_closeout_pins_exact_source_technical_execution_gates() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    local_smoke = (
        REPO_ROOT / ".github" / "workflows" / "local-smoke.yml"
    ).read_text(encoding="utf-8")
    windows_host = (
        REPO_ROOT / ".github" / "workflows" / "windows-host-tauri-dev.yml"
    ).read_text(encoding="utf-8")
    windows_installer = (
        REPO_ROOT / ".github" / "workflows" / "windows-installer.yml"
    ).read_text(encoding="utf-8")
    static_browser = (
        REPO_ROOT / "browser-tests" / "static-product-shell.spec.ts"
    ).read_text(encoding="utf-8")
    container_gate = (REPO_ROOT / "scripts" / "ci" / "run_container_gate.sh").read_text(
        encoding="utf-8"
    )
    installer_fixture = (
        REPO_ROOT / "scripts" / "ci" / "run_windows_installer_supported_upgrade.ps1"
    ).read_text(encoding="utf-8")

    for label in (
        "Windows installer",
        "Docker Browser Run",
        "Docker contributor development",
        "Windows Host Tauri dev",
    ):
        assert label in readme

    for marker in (
        "SOURCE_SHA: ${{ github.event.pull_request.head.sha || github.sha }}",
        "SOURCE_REPOSITORY: ${{ github.event.pull_request.head.repo.full_name || github.repository }}",
        "git clone --filter=blob:none --no-checkout",
        'git -C "$clean_clone" checkout --detach "$SOURCE_SHA"',
        'git -C "$clean_clone" rev-parse HEAD',
        "status --porcelain --untracked-files=all",
        'ANGMOO_SOURCE_SHA="$SOURCE_SHA"',
        "bash scripts/ci/run_container_gate.sh",
    ):
        assert marker in local_smoke
    assert 'revision="${ANGMOO_SOURCE_SHA:-${GITHUB_SHA:-$(git rev-parse HEAD)}}"' in container_gate
    assert "--development" in container_gate
    assert "contributor_dev=true" in container_gate
    assert "tests/test_l4_pr_f_closeout_contract.py" in local_smoke
    assert "tests\\test_l4_pr_f_closeout_contract.py" in windows_host
    assert "tests\\test_l4_pr_f_closeout_contract.py" in windows_installer
    assert (
        "            tests/world_packages/test_import_commit.py \\"
        in local_smoke
    )
    windows_import_fixture = (
        "            tests\\world_packages\\test_import_commit.py `"
    )
    assert windows_import_fixture in windows_host
    assert "tests\\world_packages\\test_import_commit.py" in windows_installer
    host_workflow = yaml.safe_load(windows_host)
    host_checkout = next(
        step
        for step in host_workflow["jobs"]["tauri-windows-host-dev"]["steps"]
        if str(step.get("uses", "")).startswith("actions/checkout@")
    )
    assert host_checkout["with"]["repository"] == "${{ env.SOURCE_REPOSITORY }}"
    assert host_checkout["with"]["ref"] == "${{ env.SOURCE_SHA }}"
    for marker in (
        "installed relationship graph distinguishes outage, replay, and recovery",
        'data-relationship-graph-state="degraded"',
        'data-relationship-graph-state="failed"',
        'data-relationship-graph-state="rebuilding"',
        "관계망 최신 상태",
    ):
        assert marker in static_browser

    installer_workflow = yaml.safe_load(windows_installer)
    jobs = installer_workflow["jobs"]
    verification = next(
        step for step in jobs["release-candidate"]["steps"]
        if step.get("name") == "Verify native PostgreSQL, migration input, and installer safety contracts"
    )["run"]
    # A pytest failure must stop this multi-command PowerShell step before
    # a later successful checker can replace its process exit code.
    assert verification.index("$ErrorActionPreference = 'Stop'") < verification.index("-m pytest")
    assert verification.index("$PSNativeCommandUseErrorActionPreference = $true") < verification.index("-m pytest")
    for job_id in (
        "release-candidate",
        "windows-installer-supported-upgrade",
        "windows-installer-failure-recovery",
        "windows-installer-representative-upgrade",
    ):
        checkout = next(
            step
            for step in jobs[job_id]["steps"]
            if str(step.get("uses", "")).startswith("actions/checkout@")
        )
        assert checkout["with"]["repository"] == "${{ env.SOURCE_REPOSITORY }}"
        assert checkout["with"]["ref"] == "${{ env.SOURCE_SHA }}"

    assert "$env:GITHUB_SHA" not in windows_installer
    assert "angmoo-windows-installer-${{ github.sha }}" not in windows_installer
    candidate_name = "angmoo-windows-installer-${{ env.SOURCE_SHA }}-${{ github.run_attempt }}"
    publisher = next(
        step for step in jobs["release-candidate"]["steps"]
        if step.get("name") == "Upload release-candidate evidence"
    )
    assert publisher["with"]["name"] == candidate_name
    candidate_consumers = (
        "installed-runtime-smoke",
        "windows-installer-supported-upgrade",
        "windows-installer-failure-recovery",
        "windows-installer-representative-upgrade",
    )
    for job_id in candidate_consumers:
        downloads = [
            step for step in jobs[job_id]["steps"]
            if str(step.get("uses", "")).startswith("actions/download-artifact@")
            and str(step.get("with", {}).get("name", "")).startswith("angmoo-windows-installer-")
        ]
        assert len(downloads) == 1
        assert downloads[0]["with"]["name"] == candidate_name
    assert "--commit $env:SOURCE_SHA" in windows_installer
    assert "--source-sha $env:SOURCE_SHA" in (REPO_ROOT / "scripts/ci/run_windows_postgresql_qualification.ps1").read_text(encoding="utf-8")
    assert "-Kind upgrade-013" in windows_installer
    assert "-Kind failure-recovery" in windows_installer
    assert jobs["windows-installer"]["needs"] == [
        "impact",
        "release-candidate",
        "installed-runtime-smoke",
        "windows-installer-supported-upgrade",
        "windows-installer-failure-recovery",
        "windows-installer-representative-upgrade",
    ]

    qualification = (REPO_ROOT / "scripts/ci/run_windows_postgresql_qualification.py").read_text(encoding="utf-8")
    wrapper = (REPO_ROOT / "scripts/ci/run_windows_postgresql_qualification.ps1").read_text(encoding="utf-8")
    # The current NSIS matrix owns a disposable hosted profile and synthetic
    # source, and verifies the exact installer before invoking it.
    for marker in (
        "RUNNER_ENVIRONMENT -cne 'github-hosted'",
        "windows_pg_installer_checksums_mismatch",
        "--installer-sha256 $digest --source-sha $env:SOURCE_SHA",
        "windows_pg_installer_changed",
    ):
        assert marker in wrapper
    assert "'RUNNER_ENVIRONMENT')=='github-hosted'" in qualification
    assert "windows_pg_existing_installation_refused" in qualification
    assert "windows_pg_legacy_user_data_refused" in qualification
    assert "windows_pg_private_path_invalid" in qualification
    assert "windows_pg_official_source_hash_mismatch" in qualification
    assert "windows_pg_empty_source_fixture" in qualification
    assert qualification.index("data=hosted_root()") < qualification.index("nsis(args.installer)")
    assert qualification.index("windows_pg_installer_hash_mismatch") < qualification.index("nsis(args.installer)")
    for job_id in candidate_consumers:
        native_steps = [step for step in jobs[job_id]["steps"]
            if "run_windows_postgresql_qualification.ps1" in str(step.get("run", ""))]
        assert len(native_steps) == 1
        assert "-Python (Resolve-Path 'backend/.venv/Scripts/python.exe').Path" in native_steps[0]["run"]
