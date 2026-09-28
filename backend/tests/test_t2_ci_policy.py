from __future__ import annotations

import importlib.util
import copy
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = REPO_ROOT / "scripts/check_ci_policy.py"
SPEC = importlib.util.spec_from_file_location("angmoo_t2_ci_policy", CHECKER_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def test_current_local_oss_workflow_policy_passes() -> None:
    assert checker.check_repo(REPO_ROOT) == []


def test_core_reports_reject_database_or_directory_uploads() -> None:
    path = REPO_ROOT / ".github/workflows/ci.yml"
    text = path.read_text(encoding="utf-8")
    document = checker.yaml.load(text, Loader=checker._UniqueKeyLoader)
    assert checker.check_report_uploads(document, "ci.yml", text) == []
    for unsafe_path in ("browser-tests/.ci/canonical.sqlite3", "browser-tests/.ci/"):
        changed = copy.deepcopy(document)
        uploads = [step for step in changed["jobs"]["frontend"]["steps"]
                   if str(step.get("uses", "")).startswith("actions/upload-artifact@")]
        assert len(uploads) == 1
        uploads[0]["with"]["path"] += "\n" + unsafe_path
        assert checker.check_report_uploads(changed, "ci.yml", text) == [
            "raw artifact upload is limited to the installer or exact Core test reports"
        ]


def test_required_checks_use_embedded_data_migration() -> None:
    assert "architecture-boundary" in checker.REQUIRED_JOBS
    assert "embedded-data-migration" in checker.REQUIRED_JOBS
    assert "sqlite-canonical-migration" not in checker.REQUIRED_JOBS
    assert len(checker.REQUIRED_JOBS) == 10
    assert checker.ADVISORY_JOBS == {"windows-local-smoke"}
    assert "release-images.yml" in checker.EXPECTED_WORKFLOWS
    assert "native-runtime-spike.yml" in checker.EXPECTED_WORKFLOWS
    assert "windows-host-tauri-dev.yml" in checker.EXPECTED_WORKFLOWS
    assert "windows-installer.yml" in checker.EXPECTED_WORKFLOWS


def test_unpinned_action_and_conditional_required_job_are_rejected(tmp_path: Path) -> None:
    workflow = tmp_path / "workflow.yml"
    workflow.write_text(
        """
name: fixture
on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  backend:
    if: always()
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4
""".lstrip(),
        encoding="utf-8",
    )

    errors, _ = checker.check_workflow(workflow)

    assert any("full commit SHA" in error for error in errors)
    assert any("conditionally skipped" in error for error in errors)

def test_release_workflow_rejects_pull_request_and_branch_triggers(tmp_path: Path) -> None:
    workflow = tmp_path / "release-images.yml"
    workflow.write_text(
        """
name: release
on:
  push:
    branches: [main]
  pull_request:
permissions:
  contents: read
jobs:
  publish-ghcr:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps: []
""".lstrip(),
        encoding="utf-8",
    )

    errors, _ = checker.check_workflow(workflow)

    assert any("triggered only by push" in error for error in errors)
