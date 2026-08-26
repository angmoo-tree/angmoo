from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_SMOKE = REPO_ROOT / ".github" / "workflows" / "local-smoke.yml"
SECURITY = REPO_ROOT / ".github" / "workflows" / "security.yml"
WINDOWS_HOST = (
    REPO_ROOT / ".github" / "workflows" / "windows-host-tauri-dev.yml"
)
WINDOWS_INSTALLER = (
    REPO_ROOT / ".github" / "workflows" / "windows-installer.yml"
)
SCANNER = REPO_ROOT / "scripts" / "ci" / "check_world_package_exclusions.py"
SCANNER_CORE = (
    REPO_ROOT
    / "backend"
    / "app"
    / "domains"
    / "world_packages"
    / "application"
    / "exclusion_scan.py"
)
EVIDENCE = (
    REPO_ROOT / "docs" / "architecture" / "l3-5-world-package-closeout.md"
)
USER_GUIDE = REPO_ROOT / "docs" / "public" / "world-package-v1.md"
README = REPO_ROOT / "README.md"
CONTRIBUTING = REPO_ROOT / "CONTRIBUTING.md"
CORE_CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
FRONTEND_PACKAGE = REPO_ROOT / "frontend" / "package.json"
PROXY_SMOKE = REPO_ROOT / "frontend" / "scripts" / "test-world-package-proxy.mjs"


WORLD_PACKAGE_SUITES = (
    "tests/test_l3_5_world_package_v1_contract.py",
    "tests/test_l3_5_world_package_export.py",
    "tests/test_l3_5_world_package_preview.py",
    "tests/test_l3_5_world_package_import_commit.py",
    "tests/test_l3_5_world_package_ui_contract.py",
    "tests/test_l3_5_world_package_closeout.py",
    "tests/test_l3_5_world_package_closeout_contract.py",
)


def test_required_linux_workflows_pin_the_closeout_suite() -> None:
    local_smoke = LOCAL_SMOKE.read_text(encoding="utf-8")
    security = SECURITY.read_text(encoding="utf-8")
    for test_file in WORLD_PACKAGE_SUITES:
        assert test_file in local_smoke
    for test_file in (
        "tests/test_l3_5_world_package_v1_contract.py",
        "tests/test_l3_5_world_package_preview.py",
        "tests/test_l3_5_world_package_closeout.py",
        "tests/test_l3_5_world_package_closeout_contract.py",
    ):
        assert test_file in security


def test_windows_product_paths_pin_file_ux_and_closeout_contracts() -> None:
    for workflow_path in (WINDOWS_HOST, WINDOWS_INSTALLER):
        workflow = workflow_path.read_text(encoding="utf-8")
        assert "tests\\test_l3_5_world_package_ui_contract.py" in workflow
        assert "tests\\test_l3_5_world_package_closeout_contract.py" in workflow


def test_core_ci_runs_the_real_world_package_proxy_smoke() -> None:
    workflow = CORE_CI.read_text(encoding="utf-8")
    package = FRONTEND_PACKAGE.read_text(encoding="utf-8")
    smoke = PROXY_SMOKE.read_text(encoding="utf-8")

    assert "pnpm test:world-package-proxy" in workflow
    assert '"test:world-package-proxy"' in package
    for capability in (
        "X-World-Package-Download-Token",
        "X-World-Package-Delivery-Mode",
        "X-World-Package-Preview-Token",
    ):
        assert capability in smoke
    assert "world_package_proxy_capability_smoke_pass" in smoke


def test_exclusion_scanner_is_allow_listed_and_redacts_private_values() -> None:
    scanner = SCANNER.read_text(encoding="utf-8")
    core = SCANNER_CORE.read_text(encoding="utf-8")
    assert '"content/world.json"' in core
    assert '"content/characters.json"' in core
    assert '"content/world-characters.json"' in core
    assert '"encrypted_api_key"' in core
    assert '"relationship_state"' in core
    assert '"world_package_private_value_detected"' in core
    assert "print(marker" not in core
    assert "scan_world_package_bytes" in scanner


def test_closeout_docs_keep_private_data_and_release_gates_separate() -> None:
    evidence = EVIDENCE.read_text(encoding="utf-8")
    guide = USER_GUIDE.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    contributing = CONTRIBUTING.read_text(encoding="utf-8")

    assert "PR G LOCAL TECH, SECURITY, CLEAN-CLONE PASS" in evidence
    assert "HOSTED, USER, MERGE GATES PENDING" in evidence
    assert "source and target roots are isolated" in evidence
    assert "public Release, Nest upload, promotion, and merge" in evidence
    assert "Exporting is not backup or synchronization" in guide
    assert "Do not attach a real local World Package" in guide
    assert "SECURITY.md" in guide
    assert "Source and imported Worlds evolve" in readme
    assert "independently. Read the" in readme
    assert "Never upload a real `.angmoo-world`" in contributing
