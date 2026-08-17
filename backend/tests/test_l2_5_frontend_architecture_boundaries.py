from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = REPO_ROOT / "scripts/ci/check_frontend_architecture_boundaries.py"
SPEC = importlib.util.spec_from_file_location(
    "angmoo_l2_5_frontend_architecture", CHECKER_PATH
)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def _policy(*, exceptions: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "documentation": "docs/architecture/frontend-product-shell.md",
        "feature_names": [
            "creator-studio",
            "device-home",
            "runtime-status",
            "world-app",
        ],
        "legacy_import_exceptions": exceptions or [],
        "legacy_import_prefixes": ["@/components", "@/lib"],
        "policy_id": "angmoo-l2-5-frontend-product-shell-v1",
        "required_markers": {},
        "required_paths": [],
        "schema_version": 1,
    }


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_repository_frontend_boundaries_pass() -> None:
    policy = checker._load(REPO_ROOT / "security/frontend_architecture_policy.json")

    assert checker.check_frontend(REPO_ROOT / "frontend/src", policy) == []


def test_route_must_import_feature_public_entry(tmp_path: Path) -> None:
    source_root = tmp_path / "frontend/src"
    _write(
        tmp_path,
        "frontend/src/app/page.tsx",
        'import { DeviceHomeShell } from "@/features/device-home/ui/device-home-shell";',
    )

    errors = checker.check_frontend(source_root, _policy())

    assert any("[route_deep_feature_import]" in error for error in errors)
    assert any("@/features/device-home/public" in error for error in errors)


def test_cross_feature_deep_import_is_rejected(tmp_path: Path) -> None:
    source_root = tmp_path / "frontend/src"
    _write(
        tmp_path,
        "frontend/src/features/world-app/ui/world.tsx",
        'import { DeviceHomeShell } from "@/features/device-home/ui/device-home-shell";',
    )

    errors = checker.check_frontend(source_root, _policy())

    assert any("[cross_feature_deep_import]" in error for error in errors)


def test_shared_primitive_cannot_import_product_feature(tmp_path: Path) -> None:
    source_root = tmp_path / "frontend/src"
    _write(
        tmp_path,
        "frontend/src/shared/ui/device-frame.tsx",
        'import { DeviceHomeShell } from "@/features/device-home/public";',
    )

    errors = checker.check_frontend(source_root, _policy())

    assert any("[shared_imports_feature]" in error for error in errors)


def test_new_feature_cannot_add_unreviewed_legacy_import(tmp_path: Path) -> None:
    source_root = tmp_path / "frontend/src"
    _write(
        tmp_path,
        "frontend/src/features/device-home/ui/home.tsx",
        'import { AppShell } from "@/components/app-shell";',
    )

    errors = checker.check_frontend(source_root, _policy())

    assert any("[feature_imports_legacy_layer]" in error for error in errors)


def test_exact_legacy_exception_must_be_used(tmp_path: Path) -> None:
    source_root = tmp_path / "frontend/src"
    exception = {
        "importer": "frontend/src/features/device-home/ui/home.tsx",
        "target": "@/components/app-shell",
        "owner_stage": "L2.5",
        "removal_condition": "Remove after the route migration.",
    }
    _write(
        tmp_path,
        exception["importer"],
        f'import {{ AppShell }} from "{exception["target"]}";',
    )

    assert checker.check_frontend(
        source_root, _policy(exceptions=[exception])
    ) == []

    _write(tmp_path, exception["importer"], "export const home = true;")
    errors = checker.check_frontend(source_root, _policy(exceptions=[exception]))
    assert any("[stale_frontend_exception]" in error for error in errors)
