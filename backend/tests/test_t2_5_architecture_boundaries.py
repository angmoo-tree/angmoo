from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = REPO_ROOT / "scripts/ci/check_architecture_boundaries.py"
SPEC = importlib.util.spec_from_file_location("angmoo_t2_5_architecture", CHECKER_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def _module(
    name: str,
    *,
    imports: tuple[str, ...] = (),
    external: tuple[str, ...] = (),
    wildcard: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "external_imports": sorted(external),
        "imports": sorted(imports),
        "module": name,
        "path": f"backend/{name.replace('.', '/')}.py",
        "wildcard_imports": sorted(wildcard),
    }


def _inventory(*modules: dict[str, Any]) -> dict[str, Any]:
    ordered = sorted(modules, key=lambda item: item["module"])
    return {
        "edge_count": sum(len(item["imports"]) for item in ordered),
        "external_import_count": sum(
            len(item["external_imports"]) for item in ordered
        ),
        "module_count": len(ordered),
        "modules": ordered,
        "purpose": "test fixture",
        "root": "backend/app",
        "schema_version": 2,
    }


def _policy(
    *,
    exception_groups: list[dict[str, Any]] | None = None,
    legacy_cycles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "documentation": "docs/architecture/backend-domains.md",
        "legacy_exception_groups": exception_groups or [],
        "legacy_module_cycles": legacy_cycles or [],
        "legacy_prefixes": [
            "app.cruds",
            "app.models",
            "app.schemas",
            "app.services",
        ],
        "new_area_prefixes": [
            "app.domains",
            "app.integrations",
            "app.runtime",
        ],
        "owner_stages": ["L0", "L1", "L2", "L3", "L4", "L6", "P8-L", "T2.5"],
        "policy_id": "angmoo-t2-5-domain-first-v1",
        "provider_sdk_prefixes": ["google", "oci", "replicate"],
        "schema_version": 1,
    }


def _exception(
    importer: str, imported: str, *, owner_stage: str = "L6"
) -> dict[str, Any]:
    return {
        "edges": [{"imported": imported, "importer": importer}],
        "id": "fixture-exception",
        "owner_stage": owner_stage,
        "reason": "Exact pre-policy fixture edge.",
        "removal_condition": "Remove when the fixture migrates to a public API.",
        "review_date": "2026-11-14",
    }


def _cycle(*modules: str) -> dict[str, Any]:
    return {
        "id": "fixture-cycle",
        "modules": sorted(modules),
        "owner_stage": "L6",
        "reason": "Exact pre-policy fixture cycle.",
        "removal_condition": "Break the fixture cycle through a public API.",
        "review_date": "2026-11-14",
    }


def test_valid_domain_public_dependency_passes() -> None:
    inventory = _inventory(
        _module("app.core.config"),
        _module("app.domains.alpha.public"),
        _module(
            "app.domains.alpha.use_case",
            imports=("app.core.config", "app.domains.beta.public"),
        ),
        _module("app.domains.beta.public"),
    )

    assert checker.check_inventory(inventory, _policy()) == []


def test_cross_domain_deep_import_fails_with_actionable_message() -> None:
    inventory = _inventory(
        _module(
            "app.domains.alpha.use_case",
            imports=("app.domains.beta.internal",),
        ),
        _module("app.domains.beta.internal"),
        _module("app.domains.beta.public"),
    )

    errors = checker.check_inventory(inventory, _policy())

    assert any("[cross_domain_deep_import]" in error for error in errors)
    assert any(
        "app.domains.alpha.use_case -> app.domains.beta.internal" in error
        for error in errors
    )
    assert any("allowed_fix=import app.domains.beta.public" in error for error in errors)
    assert any("legacy_exception=no" in error for error in errors)


def test_domain_provider_sdk_import_fails() -> None:
    inventory = _inventory(
        _module("app.domains.alpha.use_case", external=("google.genai",)),
    )

    errors = checker.check_inventory(inventory, _policy())

    assert any("[domain_runtime_imports_provider_sdk]" in error for error in errors)


def test_new_legacy_edge_fails_but_exact_reviewed_edge_passes() -> None:
    inventory = _inventory(
        _module("app.api.route", imports=("app.services.legacy",)),
        _module("app.services.legacy"),
    )

    errors = checker.check_inventory(inventory, _policy())
    assert any("[legacy_edge_not_allowlisted]" in error for error in errors)

    policy = _policy(
        exception_groups=[_exception("app.api.route", "app.services.legacy")]
    )
    assert checker.check_inventory(inventory, policy) == []


def test_removed_legacy_edge_requires_exception_cleanup() -> None:
    inventory = _inventory(_module("app.api.route"), _module("app.services.legacy"))
    policy = _policy(
        exception_groups=[_exception("app.api.route", "app.services.legacy")]
    )

    errors = checker.check_inventory(inventory, policy)

    assert any("[stale_legacy_exception]" in error for error in errors)


def test_new_module_cycle_fails_and_exact_legacy_cycle_passes() -> None:
    inventory = _inventory(
        _module("app.alpha", imports=("app.beta",)),
        _module("app.beta", imports=("app.alpha",)),
    )

    errors = checker.check_inventory(inventory, _policy())
    assert any("[module_cycle]" in error for error in errors)

    policy = _policy(legacy_cycles=[_cycle("app.alpha", "app.beta")])
    assert checker.check_inventory(inventory, policy) == []


def test_domain_package_cycle_fails_even_through_public_apis() -> None:
    inventory = _inventory(
        _module("app.domains.alpha.public"),
        _module(
            "app.domains.alpha.use_case",
            imports=("app.domains.beta.public",),
        ),
        _module("app.domains.beta.public"),
        _module(
            "app.domains.beta.use_case",
            imports=("app.domains.alpha.public",),
        ),
    )

    errors = checker.check_inventory(inventory, _policy())

    assert any("[package_cycle]" in error for error in errors)


def test_wildcard_import_fails() -> None:
    inventory = _inventory(
        _module("app.api.route", wildcard=("app.schemas",)),
        _module("app.schemas"),
    )

    errors = checker.check_inventory(inventory, _policy())

    assert any("[wildcard_import]" in error for error in errors)


def test_exception_metadata_rejects_wildcard_prefix() -> None:
    inventory = _inventory(_module("app.api.route"), _module("app.services.legacy"))
    exception = _exception("app.api.*", "app.services.legacy")

    errors = checker.check_inventory(
        inventory,
        _policy(exception_groups=[exception]),
    )

    assert any("must not use wildcard prefixes" in error for error in errors)
