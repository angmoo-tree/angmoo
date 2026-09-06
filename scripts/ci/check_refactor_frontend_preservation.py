"""Freeze the PR290 frontend stock and preserve its consumers during AR-F2..F5.

This supplements, rather than replaces, the backend/source preservation gate.
Source mappings prove coverage; browser assertions, fixtures and snapshots stay
unchanged except for explicit source-path moves. Browser execution proves UI parity.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile


ROOT = Path(__file__).resolve().parents[2]
BASE = "33e9df8593272f6c81236c477ae73ef057d0d3dd"
CHECKPOINT = "security/refactor_frontend_checkpoint.json"
PATH_MAP = "security/refactor_path_map.json"
FEATURE_STAGES = {
    "device-home": "AR-F1", "device-shell": "AR-F2-C", "pwa-shell": "AR-F2-C",
    "world-app": "AR-F2-C", "runtime-status": "AR-F2-C",
    "characters": "AR-F3-B", "creator-studio": "AR-F3-C",
    "world-packages": "AR-F3-D", "social": "AR-F3-E",
    "relationships": "AR-F3-F", "chat": "AR-F4-A", "memory": "AR-F4-B",
    "ui-foundation": "AR-F5-A",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def scope(path: str) -> bool:
    return path.startswith(("frontend/", "browser-tests/"))


def classification(path: str) -> tuple[str, str]:
    if path.startswith("browser-tests/"):
        return "test-or-fixture", "AR-F5-A"
    if path.startswith("frontend/public/"):
        return "public-asset", "AR-F5-A"
    if path.startswith("frontend/src/features/"):
        return "feature", FEATURE_STAGES[path.split("/")[3]]
    if path.startswith("frontend/src/shared/ui/"):
        return "common-ui", "AR-F2-A"
    if path.startswith("frontend/src/shared/"):
        return "transport-or-platform", "AR-F2-B"
    if path.startswith("frontend/src/composition/"):
        return "screen-composition", "AR-F2-C"
    if path.startswith("frontend/src/app/"):
        return "next-entry-or-screen", "AR-F2-C"
    name = Path(path).stem
    if path.startswith(("frontend/src/components/", "frontend/src/lib/")):
        groups = (
            ("AR-F3-A", ("auth", "login", "owner", "settings", "profile-setup", "user-profile", "turnstile")),
            ("AR-F3-C", ("world-creator", "worlds")),
            ("AR-F3-B", ("agent", "character", "activity")),
            ("AR-F3-G", ("tree", "angmoo-api", "policy-links", "seo")),
            ("AR-F4-A", ("message",)),
            ("AR-F2-C", ("app-shell", "features")),
            ("AR-F2-B", ("backend", "safe-", "use-", "navigation", "runtime", "incremental")),
        )
        for stage, names in groups:
            if any(name.startswith(prefix) for prefix in names):
                return "existing-owner-to-separate", stage
        if "/components/ui/" in path:
            return "canonical-common", "AR-F2-A"
        return "social-or-shared-presentation", "AR-F3-E"
    return "build-config-or-support", "AR-F5-A"


def committed_files(root: Path = ROOT) -> dict[str, bytes]:
    archive = subprocess.check_output(
        ["git", "-c", "core.autocrlf=false", "-c", "core.eol=lf",
         "archive", "--format=tar", BASE, "frontend", "browser-tests"], cwd=root,
    )
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        return {member.name: tar.extractfile(member).read()
                for member in tar.getmembers() if member.isfile()}


def snapshot(files: dict[str, bytes]) -> dict:
    return {
        "schema_version": 1,
        "commit": BASE,
        "purpose": "Immutable PR290 frontend stock; paths move in refactor_path_map, not in this checkpoint.",
        "files": {
            path: {"sha256": digest(data), "kind": classification(path)[0],
                   "owner_stage": classification(path)[1]}
            for path, data in sorted(files.items())
        },
        "next_entries": sorted(path for path in files
                               if path.startswith("frontend/src/app/")
                               and Path(path).name in {"page.tsx", "layout.tsx", "route.ts", "manifest.ts"}),
        "static_entry": "frontend/src/composition/static-product-router.tsx",
        "browser_configs": sorted(path for path in files if "/playwright." in path),
        "scope_note": "Route capabilities and expected states remain asserted in the frozen browser tests and fixtures; file existence is not runtime PASS.",
    }


def mapped(path: str, moves: dict[str, str]) -> str:
    visited = set()
    while path in moves and moves[path] != path:
        if path in visited:
            raise ValueError(f"cyclic frontend path mapping: {path}")
        visited.add(path)
        path = moves[path]
    if Path(path).is_absolute() or path.startswith("/") or re.match(r"^[A-Za-z]:", path) or ".." in path.split("/") or "\\" in path:
        raise ValueError(f"unsafe frontend target: {path}")
    return path


def rewrite_paths(text: str, moves: dict[str, str]) -> str:
    """Only quoted module/source paths change; assertions and limits remain exact."""
    replacements = {}
    for old in moves:
        new = mapped(old, moves)
        replacements[old] = new
        if old.startswith("frontend/src/") and new.startswith("frontend/src/"):
            for prefix in ("@/", "src/"):
                a, b = prefix + old[13:], prefix + new[13:]
                replacements[a] = b
                if a.endswith((".ts", ".tsx")):
                    replacements[a.rsplit(".", 1)[0]] = b.rsplit(".", 1)[0]
    return re.sub(r"(['\"])([^'\"\n]+)\1",
                  lambda m: m[1] + replacements.get(m[2], m[2]) + m[1], text)


def verify(root: Path, frozen: dict[str, bytes], moves: dict[str, str]) -> list[str]:
    errors = []
    for old, original in sorted(frozen.items()):
        new = mapped(old, moves)
        target = (root / new).resolve()
        if not target.is_relative_to(root.resolve()) or not target.is_file():
            errors.append(f"[frontend_stock_missing] {old} -> {new}")
            continue
        # Freeze test bodies, fixtures, visual oracles, dependencies, and public
        # assets. Product refactoring does not authorize changes to these oracles.
        protected = (old.startswith(("browser-tests/", "frontend/public/"))
                     or old.endswith(("package.json", "pnpm-lock.yaml"))
                     or old == "frontend/scripts/test-world-package-proxy.mjs")
        if not protected:
            continue
        current = target.read_bytes()
        if Path(old).suffix in {".png", ".ico", ".jpg", ".woff", ".woff2"}:
            equal = current == original
        else:
            expected = rewrite_paths(original.decode("utf-8"), moves).replace("\r\n", "\n")
            equal = current.decode("utf-8").replace("\r\n", "\n") == expected
        if not equal:
            errors.append(f"[frontend_oracle_changed] {old} -> {new}")
    return errors


def verify_retirements(root: Path, frozen: dict[str, bytes], moves: dict[str, str], details: dict) -> list[str]:
    """Retire a named-export facade only when every original export survives.

    This deliberately accepts only a narrow, static facade grammar. Arbitrary
    implementation files cannot be excused by pointing their old path at a
    surviving file. TypeScript and runtime tests still verify actual consumers.
    """
    errors = []
    statement = re.compile(r'''export\s+(?:type\s+)?\{([^}]+)\}\s*from\s*(['"])([^'"\n]+)\2\s*;''', re.S)
    imported = re.compile(r'''(?:from\s+|import\s*\(|require\s*\(|import\s+)\s*['"]([^'"\n]+)['"]''')
    for stage, detail in details.items():
        for old, record in detail.get("frontend_retirements", {}).items():
            if old not in frozen or not old.startswith("frontend/src/"):
                errors.append(f"[frontend_retirement_unfrozen_source] {stage}: {old}")
                continue
            source = frozen[old].decode("utf-8")
            exports = set()
            valid = True
            for match in statement.finditer(source):
                for binding in match[1].split(","):
                    if not binding.strip():
                        continue
                    symbol = re.fullmatch(r"\s*(?:type\s+)?([A-Za-z_$][\w$]*)(?:\s+as\s+([A-Za-z_$][\w$]*))?\s*", binding)
                    if symbol is None:
                        valid = False
                    else:
                        exports.add(symbol[2] or symbol[1])
            if not valid or not exports or statement.sub("", source).strip():
                errors.append(f"[frontend_retirement_not_static_facade] {old}")
                continue
            destinations = record.get("export_destinations", {})
            if set(destinations) != exports or not record.get("reason") or not record.get("verification"):
                errors.append(f"[frontend_retirement_export_coverage] {old}")
            if (root / old).exists():
                errors.append(f"[frontend_retirement_source_still_exists] {old}")
            if mapped(old, moves) not in destinations.values():
                errors.append(f"[frontend_retirement_unrelated_target] {old}")
            for name, destination in destinations.items():
                target = (root / destination).resolve()
                if not target.is_relative_to((root / "frontend/src").resolve()) or not target.is_file():
                    errors.append(f"[frontend_retirement_missing_export] {old}: {name} -> {destination}")
                    continue
                declaration = rf"\bexport\s+(?:async\s+)?(?:function|class|const|let|type|interface|enum)\s+{re.escape(name)}\b"
                if re.search(declaration, target.read_text(encoding="utf-8")) is None:
                    errors.append(f"[frontend_retirement_missing_export] {old}: {name} -> {destination}")
            retired_module = (root / old).with_suffix("").resolve()
            for folder in (root / "frontend/src", root / "frontend/static-shell/app"):
                for path in folder.rglob("*"):
                    if not path.is_file() or path.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
                        continue
                    for spec in imported.findall(path.read_text(encoding="utf-8")):
                        if spec.startswith("@/"):
                            target = root / "frontend/src" / spec[2:]
                        elif spec.startswith("."):
                            target = path.parent / spec
                        else:
                            continue
                        if target.suffix in {".ts", ".tsx", ".js", ".jsx"}:
                            target = target.with_suffix("")
                        if target.resolve() == retired_module:
                            errors.append(f"[frontend_retirement_active_import] {path.relative_to(root)} -> {old}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true")
    args = parser.parse_args()
    frozen = committed_files()
    expected = snapshot(frozen)
    path = ROOT / CHECKPOINT
    if args.capture:
        if path.exists():
            raise ValueError("frontend checkpoint exists; never overwrite frozen evidence")
        path.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"Captured PR290 frontend stock: {len(frozen)} files")
        return 0
    if json.loads(path.read_text(encoding="utf-8")) != expected:
        raise ValueError("frontend checkpoint differs from pinned PR290 Git source")
    path_map = json.loads((ROOT / PATH_MAP).read_text(encoding="utf-8"))
    moves = path_map["files"]
    errors = verify(ROOT, frozen, moves)
    errors.extend(verify_retirements(ROOT, frozen, moves, path_map.get("details", {})))
    for error in errors:
        print(error)
    if errors:
        return 1
    print(f"Frontend preservation passed: {len(frozen)} source files; browser assertions/fixtures/assets/locks preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
