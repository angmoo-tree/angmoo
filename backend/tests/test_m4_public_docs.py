from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = REPO_ROOT / "scripts" / "check_public_docs.py"
SPEC = importlib.util.spec_from_file_location("angmoo_public_docs", CHECKER_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def test_document_checker_ignores_next_route_directories_named_markdown(
    tmp_path: Path,
) -> None:
    for relative in checker.REQUIRED:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        markers = checker.REQUIRED_MARKERS.get(relative, ())
        target.write_text(
            "# test\n" + "\n".join(markers) + "\n",
            encoding="utf-8",
        )
    route_directory = tmp_path / "frontend/src/app/agent_guide.md"
    route_directory.mkdir(parents=True)
    (route_directory / "route.ts").write_text("export {};\n", encoding="utf-8")

    assert checker.check(tmp_path) == []


def test_document_checker_rejects_missing_bilingual_required_marker(
    tmp_path: Path,
) -> None:
    for relative in checker.REQUIRED:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        markers = checker.REQUIRED_MARKERS.get(relative, ())
        target.write_text(
            "# test\n" + "\n".join(markers) + "\n",
            encoding="utf-8",
        )
    (tmp_path / "README.ko.md").write_text("# Angmoo\n", encoding="utf-8")

    assert any(
        error.startswith("README.ko.md: missing required marker")
        for error in checker.check(tmp_path)
    )
