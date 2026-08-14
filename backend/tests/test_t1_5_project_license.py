from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = REPO_ROOT / "scripts" / "check_project_license.py"
SPEC = importlib.util.spec_from_file_location(
    "angmoo_t1_5_project_license", CHECKER_PATH
)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def _minimal_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "security").mkdir(parents=True)
    (root / "backend").mkdir()
    (root / "frontend").mkdir()
    shutil.copyfile(REPO_ROOT / "LICENSE", root / "LICENSE")
    (root / "README.md").write_text(
        "GPL-3.0-only application declaration\n",
        encoding="utf-8",
    )
    (root / "backend/pyproject.toml").write_text(
        '[project]\nname = "fixture"\nversion = "0.1.0"\nlicense = "GPL-3.0-only"\n',
        encoding="utf-8",
    )
    (root / "frontend/package.json").write_text(
        json.dumps({"name": "fixture", "private": True, "license": "GPL-3.0-only"}),
        encoding="utf-8",
    )
    (root / "seed.txt").write_text("synthetic\n", encoding="utf-8")
    (root / "references.txt").write_text("fixture-reference\n", encoding="utf-8")
    (root / "asset.bin").write_bytes(b"first-party-asset")

    policy = json.loads(
        (REPO_ROOT / "security/license_policy.json").read_text(encoding="utf-8")
    )
    policy["project"]["declarations"] = [
        {
            "path": "README.md",
            "required": ["GPL-3.0-only"],
            "forbidden": ["Apache License 2.0"],
        }
    ]
    policy["project"]["forbidden_current_legal_files"] = ["NOTICE"]
    policy["bundled_content"] = [
        {
            "path": "seed.txt",
            "classification": "first-party synthetic fixture",
            "license_expression": "GPL-3.0-only",
        }
    ]
    policy["infrastructure"] = [
        {
            "name": "Fixture database",
            "source_path": "references.txt",
            "reference": "fixture-reference",
            "license_expression": "PostgreSQL",
            "distribution_boundary": "Independent service.",
            "source": "https://example.invalid/database-license",
        }
    ]
    policy["actions"] = [
        {
            "name": "Fixture action",
            "source_path": "references.txt",
            "reference": "fixture-reference",
            "license_expression": "MIT",
            "source": "https://example.invalid/action-license",
        }
    ]
    policy["assets"] = [
        {
            "name": "Fixture asset",
            "path": "asset.bin",
            "sha256": hashlib.sha256(b"first-party-asset").hexdigest(),
            "license_expression": "GPL-3.0-only",
            "note": "First-party fixture.",
        }
    ]
    (root / "security/license_policy.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )

    notice_markers = [
        "## Reviewed conditional dependencies",
        "## Infrastructure and build tooling",
        "## Bundled assets and content",
        "Fixture database",
        "Fixture action",
        "Fixture asset",
    ]
    notice_markers.extend(
        f"{record['name']} {record['version']}"
        for record in policy["dependency_reviews"]
    )
    (root / "THIRD_PARTY_NOTICES.md").write_text(
        "\n".join(notice_markers) + "\n", encoding="utf-8"
    )
    return root


def test_current_repository_license_surface_is_valid() -> None:
    assert checker.check(REPO_ROOT) == []


def test_minimal_valid_repository_passes(tmp_path: Path) -> None:
    root = _minimal_repo(tmp_path)

    assert checker.check(root) == []


def test_rejects_gpl_or_later_project_metadata(tmp_path: Path) -> None:
    root = _minimal_repo(tmp_path)
    (root / "backend/pyproject.toml").write_text(
        '[project]\nname = "fixture"\nversion = "0.1.0"\nlicense = "GPL-3.0-or-later"\n',
        encoding="utf-8",
    )

    assert "backend project license must be GPL-3.0-only" in checker.check(root)


def test_rejects_obsolete_notice(tmp_path: Path) -> None:
    root = _minimal_repo(tmp_path)
    (root / "NOTICE").write_text("obsolete\n", encoding="utf-8")

    assert "obsolete or historical legal file must not exist: NOTICE" in checker.check(root)


def test_rejects_modified_gpl_text(tmp_path: Path) -> None:
    root = _minimal_repo(tmp_path)
    (root / "LICENSE").write_text("modified\n", encoding="utf-8")

    assert "LICENSE is not the official GNU GPL version 3 text" in checker.check(root)
