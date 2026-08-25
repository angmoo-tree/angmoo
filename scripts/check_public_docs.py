"""Check public documentation links and required governance files."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from urllib.parse import unquote


REQUIRED = {
    ".github/PULL_REQUEST_TEMPLATE.md",
    "README.md",
    "README.ko.md",
    "LICENSE",
    "BRANDING.md",
    "THIRD_PARTY_NOTICES.md",
    "CONTRIBUTING.md",
    "CONTRIBUTING.ko.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "docs/public/architecture.md",
    "docs/public/development.md",
    "docs/public/security.md",
}
REQUIRED_MARKERS = {
    "README.md": (
        "English | [한국어](README.ko.md)",
        "The English documents are the canonical source",
        "## Public v0.3 scope",
        "## Quickstart",
        "## Known limitations",
        "It is not yet a long-term memory system",
        "GPL-3.0-only",
        "[LICENSE](LICENSE)",
        "[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)",
        "user-created or imported World Package",
        "local runtime data",
    ),
    "README.ko.md": (
        "[English](README.md) | 한국어",
        "영어 문서를 기준으로 합니다",
        "## 공개 v0.3 범위",
        "## 빠른 시작",
        "## 알려진 한계",
        "장기 메모리 시스템은 아직 아닙니다",
        "[한국어 기여 가이드](CONTRIBUTING.ko.md)",
        "GPL-3.0-only",
        "[LICENSE](LICENSE)",
        "[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)",
        "World Package",
        "Runtime 데이터",
    ),
    "CONTRIBUTING.md": (
        "Issues and pull requests may be written in English or Korean",
        "`CONTRIBUTOR_EMBEDDED`",
        "SQLite is the only canonical store",
        "GPL-3.0-only",
        "Developer Certificate of Origin 1.1",
        "git commit -s",
        "Signed-off-by",
    ),
    "CONTRIBUTING.ko.md": (
        "한국어와 영어 모두 사용할 수 있습니다",
        "## 개발 환경",
        "## Issue와 작업 범위",
        "## Branch, commit과 Pull Request",
        "`CONTRIBUTOR_EMBEDDED`",
        "`sqlite-canonical-migration`",
        "GPL-3.0-only",
        "Developer Certificate of Origin 1.1",
        "git commit -s",
        "Signed-off-by",
    ),
    ".github/PULL_REQUEST_TEMPLATE.md": (
        "SQLite / FTS5 / LadybugDB migration, replay, or graph checks",
        "SQLite canonical baseline, generation lifecycle",
        "GPL-3.0-only",
        "DCO 1.1",
        "Signed-off-by",
    ),
    "BRANDING.md": (
        "GPL-3.0-only",
        "not the Angmoo name, logo",
    ),
    "THIRD_PARTY_NOTICES.md": (
        "## Reviewed conditional dependencies",
        "## Infrastructure and build tooling",
        "## Bundled assets and content",
        "## License scope boundary",
    ),
    "SECURITY.md": (
        "GitHub Private Vulnerability Reporting",
        "## 한국어 신고 안내",
        "신고는 한국어나 영어로 작성할 수 있습니다",
    ),
}
LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
EXCLUDED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
}


def check(root: Path) -> list[str]:
    root = root.resolve()
    errors = [
        f"missing required document: {path}"
        for path in sorted(REQUIRED)
        if not (root / path).is_file()
    ]
    for relative, markers in sorted(REQUIRED_MARKERS.items()):
        document = root / relative
        if not document.is_file():
            continue
        text = document.read_text(encoding="utf-8")
        errors.extend(
            f"{relative}: missing required marker {marker}"
            for marker in markers
            if marker not in text
        )
    for document in sorted(root.rglob("*.md")):
        if not document.is_file():
            continue
        if any(
            part in EXCLUDED_DIRECTORIES
            for part in document.relative_to(root).parts
        ):
            continue
        text = document.read_text(encoding="utf-8")
        for raw_target in LINK.findall(text):
            target = raw_target.strip().strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            target = unquote(target.split("#", 1)[0])
            if not target:
                continue
            if re.match(r"^[A-Za-z]:[\\/]", target) or target.startswith(("/", "\\")):
                errors.append(
                    f"{document.relative_to(root).as_posix()}: absolute local link {target}"
                )
                continue
            resolved = (document.parent / target).resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                errors.append(
                    f"{document.relative_to(root).as_posix()}: escaping link {target}"
                )
                continue
            if not resolved.exists():
                errors.append(
                    f"{document.relative_to(root).as_posix()}: broken link {target}"
                )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        errors = check(args.root)
    except OSError as exc:
        print(f"Public documentation check failed: {exc}", file=sys.stderr)
        return 1
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print("Public documentation check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
