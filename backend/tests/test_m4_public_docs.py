from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import re
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = REPO_ROOT / "scripts" / "check_public_docs.py"
SPEC = importlib.util.spec_from_file_location("angmoo_public_docs", CHECKER_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def test_current_release_readmes_keep_bilingual_scope_and_limitations() -> None:
    for relative in ("README.md", "README.ko.md"):
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        normalized = re.sub(r"\s+", " ", text)
        missing = [marker for marker in checker.REQUIRED_MARKERS[relative] if re.sub(r"\s+", " ", marker) not in normalized]
        assert not missing, (relative, missing)
        assert "Angmoo_0.1.0_x64-setup.exe" in text
        assert "release-v0.1.0/install-termux.py" in text


def test_document_checker_requires_memory_and_android_limitations(tmp_path: Path) -> None:
    for relative in checker.REQUIRED:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(checker.REQUIRED_MARKERS.get(relative, ())), encoding="utf-8")
    for relative, missing in (
        ("README.md", "A saved memory is not necessarily retrieved or used in every response."),
        ("README.ko.md", "모든 휴대폰에서 지속 실행을 보장하지 않습니다."),
    ):
        target = tmp_path / relative
        target.write_text(target.read_text(encoding="utf-8").replace(missing, ""), encoding="utf-8")
        assert f"{relative}: missing required marker {missing}" in checker.check(tmp_path)


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

def test_document_checker_ignores_dependency_directories(tmp_path: Path) -> None:
    for relative in checker.REQUIRED:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        markers = checker.REQUIRED_MARKERS.get(relative, ())
        target.write_text(
            "# test\n" + "\n".join(markers) + "\n",
            encoding="utf-8",
        )

    dependency_readme = tmp_path / "frontend" / "node_modules" / "example" / "README.md"
    dependency_readme.parent.mkdir(parents=True)
    dependency_readme.write_text("[missing](not-present.md)\n", encoding="utf-8")

    assert checker.check(tmp_path) == []


@pytest.mark.parametrize("relative, missing", [
    ("CONTRIBUTING.md", "Developer Certificate of Origin 1.1"),
    ("CONTRIBUTING.ko.md", "Signed-off-by"),
    ("SECURITY.md", "Do not disclose an exploit, credential or personal data in a public Issue."),
    ("README.md", "GPL-3.0-only"),
])
def test_document_checker_preserves_governance_and_security_contracts(tmp_path, relative, missing):
    for name in checker.REQUIRED:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(checker.REQUIRED_MARKERS.get(name, ())), encoding="utf-8")
    target = tmp_path / relative
    target.write_text(target.read_text(encoding="utf-8").replace(missing, ""), encoding="utf-8")
    assert f"{relative}: missing required marker {missing}" in checker.check(tmp_path)
