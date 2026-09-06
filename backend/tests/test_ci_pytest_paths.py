"""Workflow smoke selections must follow actual moved test files."""
from pathlib import Path

import pytest

from test_t2_ci_policy import checker


@pytest.mark.parametrize("argument", [
    "tests/relationships/test_activity_proposals.py",
    r"tests\relationships\test_activity_proposals.py",
    "backend/tests/relationships/test_activity_proposals.py::test_runtime",
])
def test_workflow_accepts_actual_test_role_paths(tmp_path: Path, argument: str):
    target = tmp_path / "backend/tests/relationships/test_activity_proposals.py"
    target.parent.mkdir(parents=True)
    target.write_text("def test_runtime(): pass\n", encoding="utf-8")
    document = {"jobs": {"smoke": {"steps": [{"run": f"python -m pytest -q {argument}"}]}}}

    assert checker.check_pytest_paths(document, tmp_path) == []
    target.unlink()
    assert len(checker.check_pytest_paths(document, tmp_path)) == 1


@pytest.mark.parametrize("argument", [
    "tests/test_activity_proposal_runtime.py",
    r"tests\test_activity_proposal_runtime.py",
])
def test_workflow_rejects_old_path_even_when_moved_suite_exists(tmp_path: Path, argument: str):
    target = tmp_path / "backend/tests/relationships/test_activity_proposals.py"
    target.parent.mkdir(parents=True)
    target.write_text("def test_runtime(): pass\n", encoding="utf-8")
    document = {"jobs": {"smoke": {"steps": [{"run": f"uv run pytest -q {argument}"}]}}}

    errors = checker.check_pytest_paths(document, tmp_path)
    assert len(errors) == 1
    assert f"pytest test file is missing: {argument}" in errors[0]
