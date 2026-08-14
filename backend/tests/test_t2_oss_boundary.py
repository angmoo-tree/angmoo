from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = REPO_ROOT / "scripts/ci/check_oss_boundary.py"
SPEC = importlib.util.spec_from_file_location("angmoo_t2_oss_boundary", CHECKER_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def _minimal_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative in checker.ACTIVE_SURFACES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        markers = checker.REQUIRED_MARKERS.get(relative, ())
        path.write_text("\n".join(markers) + "\n", encoding="utf-8")
    return root


def test_current_repository_has_single_repo_contributor_boundary() -> None:
    assert checker.check_root(REPO_ROOT) == []


def test_obsolete_export_path_and_stale_marker_are_rejected(tmp_path: Path) -> None:
    root = _minimal_root(tmp_path)
    obsolete = root / "scripts/build_public_candidate.py"
    obsolete.parent.mkdir(parents=True, exist_ok=True)
    obsolete.write_text("obsolete\n", encoding="utf-8")
    (root / "CONTRIBUTING.md").write_text("hosted-impact\n", encoding="utf-8")

    errors = checker.check_root(root)

    assert any("obsolete two-repository path" in error for error in errors)
    assert any("stale hosted marker" in error for error in errors)
