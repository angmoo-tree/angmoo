from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = REPO_ROOT / "scripts" / "check_dependency_licenses.py"
SPEC = importlib.util.spec_from_file_location(
    "angmoo_dependency_licenses", CHECKER_PATH
)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def _write_lock(tmp_path: Path, packages: list[tuple[str, str]]) -> Path:
    backend = tmp_path / "backend"
    backend.mkdir()
    entries = ['version = 1', 'revision = 3']
    for name, version in [("backend", "0.1.0"), *packages]:
        entries.extend(
            [
                "",
                "[[package]]",
                f'name = "{name}"',
                f'version = "{version}"',
            ]
        )
    (backend / "uv.lock").write_text(
        "\n".join(entries) + "\n",
        encoding="utf-8",
    )
    return tmp_path


def test_python_inventory_uses_approved_platform_fallbacks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _write_lock(
        tmp_path,
        [("colorama", "0.4.6"), ("tzdata", "2026.2")],
    )
    monkeypatch.setattr(checker.importlib.metadata, "distributions", lambda: [])

    assert checker.python_inventory(repo_root) == [
        ("colorama", "0.4.6", "OSI Approved :: BSD License"),
        ("tzdata", "2026.2", "Apache-2.0"),
    ]


def test_python_inventory_rejects_unapproved_missing_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _write_lock(tmp_path, [("unexpected-platform-package", "1.0")])
    monkeypatch.setattr(checker.importlib.metadata, "distributions", lambda: [])

    with pytest.raises(
        checker.LicenseAuditError,
        match="locked Python packages are not installed: unexpected-platform-package",
    ):
        checker.python_inventory(repo_root)
