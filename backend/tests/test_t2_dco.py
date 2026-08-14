from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = REPO_ROOT / "scripts/ci/check_dco.py"
SPEC = importlib.util.spec_from_file_location("angmoo_t2_dco", CHECKER_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def _record(*, name: str = "Contributor", email: str = "person@example.com", body: str = "change"):
    return checker.CommitRecord("a" * 40, name, email, body)


def test_human_commit_requires_valid_signoff() -> None:
    assert checker.validate_record(_record(), ["README.md"]) == [
        "missing valid Signed-off-by trailer"
    ]
    signed = _record(body="change\n\nSigned-off-by: Contributor <person@example.com>")
    assert checker.validate_record(signed, ["README.md"]) == []


def test_dependabot_exception_is_limited_to_dependency_paths() -> None:
    bot = _record(
        name="dependabot[bot]",
        email="49699333+dependabot[bot]@users.noreply.github.com",
    )
    assert checker.validate_record(
        bot, ["frontend/pnpm-lock.yaml"], actor="dependabot[bot]"
    ) == []
    assert checker.validate_record(bot, ["frontend/pnpm-lock.yaml"]) == [
        "Dependabot exception rejected because changed paths are too broad"
    ]
    assert checker.validate_record(bot, ["backend/app/main.py"]) == [
        "Dependabot exception rejected because changed paths are too broad"
    ]
