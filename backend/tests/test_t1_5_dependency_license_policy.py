from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = REPO_ROOT / "scripts" / "check_dependency_licenses.py"
SPEC = importlib.util.spec_from_file_location(
    "angmoo_t1_5_dependency_licenses", CHECKER_PATH
)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def _policy(*, reviews: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "schema_version": 1,
        "license_aliases": {
            "Apache 2.0": "Apache-2.0",
            "Dual License": "MIT OR BSD-3-Clause",
        },
        "metadata_overrides": [],
        "allowed_license_ids": [
            "Apache-2.0",
            "BSD-3-Clause",
            "GPL-3.0-only",
            "LGPL-3.0-only",
            "MIT",
        ],
        "review_required_license_ids": ["GPL-3.0-only", "LGPL-3.0-only"],
        "forbidden_license_ids": [
            "AGPL-3.0-only",
            "GPL-2.0-only",
            "SSPL-1.0",
        ],
        "allowed_exceptions": [],
        "dependency_reviews": reviews or [],
    }


def _review(expression: str) -> dict[str, object]:
    return {
        "ecosystem": "python",
        "name": "reviewed-package",
        "version": "1.0",
        "reported_expression": expression,
        "normalized_expression": expression,
        "distribution_boundary": "Separate dependency.",
        "obligations": ["Preserve the dependency notice."],
        "source": "https://example.invalid/license",
    }


def test_parser_preserves_and_or_parentheses() -> None:
    licenses, exceptions = checker.parse_expression(
        "LGPL-3.0-only AND (Apache-2.0 OR MIT)"
    )

    assert licenses == {"LGPL-3.0-only", "Apache-2.0", "MIT"}
    assert exceptions == set()


def test_conditional_dependency_requires_exact_review() -> None:
    packages = [("reviewed-package", "1.0", "LGPL-3.0-only")]

    with pytest.raises(
        checker.LicenseAuditError,
        match="conditional license requires an exact package/version review",
    ):
        checker.validate_inventory("Python", packages, _policy(), "fixture-policy")

    used = checker.validate_inventory(
        "Python",
        packages,
        _policy(reviews=[_review("LGPL-3.0-only")]),
        "fixture-policy",
    )
    assert used == {("python", "reviewed-package", "1.0")}


@pytest.mark.parametrize(
    ("expression", "reason"),
    [
        ("GPL-2.0-only", "forbidden license ids: GPL-2.0-only"),
        ("AGPL-3.0-only", "forbidden license ids: AGPL-3.0-only"),
        ("LicenseRef-Unknown", "unknown license ids: LicenseRef-Unknown"),
    ],
)
def test_fail_closed_reports_package_and_reason(expression: str, reason: str) -> None:
    with pytest.raises(checker.LicenseAuditError) as error:
        checker.validate_inventory(
            "Python",
            [("blocked-package", "2.0", expression)],
            _policy(),
            "fixture-policy",
        )

    message = str(error.value)
    assert "ecosystem=python package=blocked-package@2.0" in message
    assert f"reported={expression}" in message
    assert reason in message
    assert "policy=fixture-policy" in message


def test_project_style_gpl_dependency_is_not_confused_with_lgpl() -> None:
    packages = [("reviewed-package", "1.0", "GPL-3.0-only")]
    used = checker.validate_inventory(
        "Python",
        packages,
        _policy(reviews=[_review("GPL-3.0-only")]),
        "fixture-policy",
    )

    assert used == {("python", "reviewed-package", "1.0")}
