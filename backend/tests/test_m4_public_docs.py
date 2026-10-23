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
    release_url = "https://github.com/angmoo-tree/angmoo/releases/tag/release-v0.1.0"
    for relative, badge_alt in (
        ("README.md", "Download Angmoo 0.1.0"),
        ("README.ko.md", "Angmoo 0.1.0 다운로드"),
    ):
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        normalized = re.sub(r"\s+", " ", text)
        missing = [
            marker
            for marker in checker.REQUIRED_MARKERS[relative]
            if re.sub(r"\s+", " ", marker) not in normalized
        ]
        assert not missing, (relative, missing)
        assert re.search(
            rf'<a\s+href="{re.escape(release_url)}">\s*'
            rf'<img\b[^>]*\balt="{re.escape(badge_alt)}"[^>]*>\s*</a>',
            text,
        ), (relative, "release badge must link to the published release")
        assert "Angmoo_0.1.0_x64-setup.exe" in text
        assert "release-v0.1.0/install-termux.py" in text


@pytest.mark.parametrize(
    "relative, missing",
    [
        ("README.md", "A saved memory is not necessarily retrieved or used in every response."),
        ("README.ko.md", "저장된 기억이 모든 응답에서 검색되거나 사용되는 것은 아닙니다."),
        ("README.md", "Android power management or app termination policies may interrupt it."),
        ("README.ko.md", "Android의 절전·앱 종료 정책에 따라 실행이 중단될 수 있습니다."),
    ],
)
def test_document_checker_requires_memory_and_android_limitations(
    tmp_path: Path, relative: str, missing: str,
) -> None:
    for name in checker.REQUIRED:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(checker.REQUIRED_MARKERS.get(name, ())), encoding="utf-8")
    assert checker.check(tmp_path) == []

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


@pytest.mark.parametrize(
    "relative, missing",
    [
        ("README.md", "## Limitations"),
        ("README.ko.md", "## 한계"),
        ("README.md", 'href="https://github.com/angmoo-tree/angmoo/releases/tag/release-v0.1.0"'),
        ("README.ko.md", 'href="https://github.com/angmoo-tree/angmoo/releases/tag/release-v0.1.0"'),
        ("README.md", 'alt="Download Angmoo 0.1.0"'),
        ("README.ko.md", 'alt="Angmoo 0.1.0 다운로드"'),
    ],
)
def test_document_checker_rejects_missing_bilingual_required_marker(
    tmp_path: Path, relative: str, missing: str,
) -> None:
    for name in checker.REQUIRED:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        markers = checker.REQUIRED_MARKERS.get(name, ())
        target.write_text(
            "# test\n" + "\n".join(markers) + "\n",
            encoding="utf-8",
        )
    assert checker.check(tmp_path) == []

    target = tmp_path / relative
    target.write_text(target.read_text(encoding="utf-8").replace(missing, ""), encoding="utf-8")
    assert f"{relative}: missing required marker {missing}" in checker.check(tmp_path)

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
