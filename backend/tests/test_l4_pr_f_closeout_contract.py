from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "backend" / "app"


def test_l4_social_runtime_has_one_concrete_owner_and_no_temporary_facades() -> None:
    required = (
        APP_ROOT / "domains" / "social" / "public.py",
        APP_ROOT / "domains" / "social" / "contracts" / "inbox.py",
        APP_ROOT / "domains" / "social" / "models" / "manual_writes.py",
        APP_ROOT / "runtime" / "social" / "sqlalchemy_unit_of_work.py",
        APP_ROOT / "runtime" / "social" / "sqlalchemy_inbox.py",
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
        "            tests/test_l3_5_world_package_import_commit.py \\"
        in local_smoke
    )
    windows_import_fixture = (
        "            tests\\test_l3_5_world_package_import_commit.py `"
    )
    assert windows_import_fixture in windows_host
    assert windows_import_fixture in windows_installer
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
    for job_id in (
        "release-candidate",
        "windows-installer-supported-upgrade",
        "windows-installer-failure-recovery",
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
    assert windows_installer.count("angmoo-windows-installer-${{ env.SOURCE_SHA }}") == 4
    assert "--commit $env:SOURCE_SHA" in windows_installer
    assert "$payloadIdentity.build_commit -ne $env:SOURCE_SHA" in windows_installer
    assert "-Mode Upgrade" in windows_installer
    assert "-Mode Recovery" in windows_installer
    assert jobs["windows-installer"]["needs"] == [
        "release-candidate",
        "installed-runtime-smoke",
        "windows-installer-supported-upgrade",
        "windows-installer-failure-recovery",
    ]

    guard_index = installer_fixture.index("windows_installer_hosted_runner_only")
    input_index = installer_fixture.index("foreach ($required")
    delete_index = installer_fixture.index(
        "Remove-Item -LiteralPath $productRoot -Recurse -Force"
    )
    fixture_check_index = installer_fixture.index("Assert-SyntheticFixtureArchive $Archive")
    remove_fixture_index = installer_fixture.index("Remove-IsolatedFixture", fixture_check_index)
    assert guard_index < input_index < delete_index
    assert fixture_check_index < remove_fixture_index
    assert "RUNNER_ENVIRONMENT -cne 'github-hosted'" in installer_fixture
    assert "windows_installer_hosted_sentinel_invalid" in installer_fixture
    assert "windows_installer_supported_upgrade_fixture_not_synthetic" in installer_fixture
    assert windows_installer.count("-RunSentinel $sentinel") == 2
