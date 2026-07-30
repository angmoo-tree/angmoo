from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
CLASSIFIER_PATH = REPO_ROOT / "scripts/classify_hosted_impact.py"
CI_POLICY_PATH = REPO_ROOT / "scripts/check_ci_policy.py"
SPEC = importlib.util.spec_from_file_location(
    "angmoo_hosted_impact",
    CLASSIFIER_PATH,
)
assert SPEC is not None and SPEC.loader is not None
classifier = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = classifier
SPEC.loader.exec_module(classifier)
CI_SPEC = importlib.util.spec_from_file_location(
    "angmoo_ci_policy",
    CI_POLICY_PATH,
)
assert CI_SPEC is not None and CI_SPEC.loader is not None
ci_policy = importlib.util.module_from_spec(CI_SPEC)
sys.modules[CI_SPEC.name] = ci_policy
CI_SPEC.loader.exec_module(ci_policy)


@pytest.fixture
def policy() -> dict[str, object]:
    return classifier._load_policy(
        REPO_ROOT / "security/hosted_impact_policy.json"
    )


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("CODE_OF_CONDUCT.md", "public-only"),
        ("frontend/src/app/page.tsx", "hosted-fast"),
        ("backend/app/api/v1/routes/auth.py", "hosted-full"),
        ("backend/app/alembic/versions/20260726_0066.py", "hosted-full"),
        (".github/workflows/ci.yml", "hosted-full"),
        ("backend/uv.lock", "hosted-full"),
    ],
)
def test_classifier_routes_known_paths(
    policy: dict[str, object],
    path: str,
    expected: str,
) -> None:
    result = classifier.classify_paths([path], policy)
    assert result["hosted_impact"] == expected
    assert result["unclassified_count"] == 0
    assert result["private_workflow_started"] is False


def test_classifier_uses_highest_mixed_severity(
    policy: dict[str, object],
) -> None:
    result = classifier.classify_paths(
        ["CODE_OF_CONDUCT.md", "backend/uv.lock"],
        policy,
    )
    assert result["hosted_impact"] == "hosted-full"


def test_classifier_checks_both_rename_paths(
    policy: dict[str, object],
) -> None:
    result = classifier.classify_paths(
        ["CODE_OF_CONDUCT.md", "backend/app/service.py"],
        policy,
    )
    assert result["hosted_impact"] == "hosted-fast"


def test_git_rename_includes_old_and_new_paths(
    tmp_path: Path,
    policy: dict[str, object],
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args: str) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        return completed.stdout.strip()

    git("init", "-q")
    git("config", "user.email", "fixture@example.invalid")
    git("config", "user.name", "Fixture")
    (repo / "CODE_OF_CONDUCT.md").write_text("fixture\n", encoding="utf-8")
    git("add", "--all")
    git("commit", "-q", "-m", "base")
    base = git("rev-parse", "HEAD")
    (repo / "backend/app").mkdir(parents=True)
    git("mv", "CODE_OF_CONDUCT.md", "backend/app/service.py")
    git("commit", "-q", "-m", "rename")
    head = git("rev-parse", "HEAD")

    paths = classifier.changed_paths(repo, base, head)
    assert paths == ["CODE_OF_CONDUCT.md", "backend/app/service.py"]
    assert classifier.classify_paths(paths, policy)["hosted_impact"] == (
        "hosted-fast"
    )


@pytest.mark.parametrize(
    "paths",
    [
        ["unexpected-root.txt"],
        ["../escape.py"],
        ["backend\\app\\main.py"],
        ["frontend/A.ts", "frontend/a.ts"],
    ],
)
def test_classifier_fails_closed(
    policy: dict[str, object],
    paths: list[str],
) -> None:
    with pytest.raises(classifier.HostedImpactError):
        classifier.classify_paths(paths, policy)


def test_public_ci_policy_accepts_current_workflow() -> None:
    assert ci_policy.check(REPO_ROOT / ".github/workflows/ci.yml") == []


def test_public_ci_policy_rejects_duplicate_yaml_keys(tmp_path: Path) -> None:
    workflow = tmp_path / "ci.yml"
    workflow.write_text(
        """
name: Duplicate
permissions:
  contents: read
jobs:
  hosted-impact: {}
  backend-contract: {}
  frontend: {}
  quickstart: {}
  security-export:
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd
        with:
          persist-credentials: false
        with:
          fetch-depth: 0
  dependency-audit: {}
""",
        encoding="utf-8",
    )
    errors = ci_policy.check(workflow)
    assert any("duplicate key 'with'" in error for error in errors)


@pytest.mark.parametrize(
    "marker",
    [
        "pull_request_target:",
        "repository_dispatch:",
        "secrets: inherit",
        "${{ secrets.ANYTHING }}",
        "jingujeon/angmoo-private",
        "permissions: write",
    ],
)
def test_public_ci_policy_rejects_private_or_write_features(
    tmp_path: Path,
    marker: str,
) -> None:
    source = (REPO_ROOT / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    workflow = tmp_path / "ci.yml"
    workflow.write_text(source + f"\n# {marker}\n", encoding="utf-8")
    assert ci_policy.check(workflow)
