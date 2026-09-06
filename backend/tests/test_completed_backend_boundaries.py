import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "completed_backend_fixtures", ROOT / "backend/tests/test_t2_5_architecture_boundaries.py",
)
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


def completed_policy():
    policy = b._policy()
    policy["refactor"] = {
        "complete": True, "domains": ["sample"], "modules": [],
        "globals": ["app.models"], "entries": [], "bridges": [],
        "retained_modules": [],
    }
    return policy


def retained(module):
    return {"module": module, "kind": "historical_migration",
            "reason": "Original immutable revision imports this exact helper.",
            "contract": "docs/architecture/backend-compatibility.md"}


def test_complete_scope_accepts_flat_ownership_and_new_files_in_the_same_role():
    inventory = b._inventory(
        b._module("app.models", external=("sqlalchemy",)),
        b._module("app.domains.sample.service"),
        b._module("app.domains.sample.service.new_flow"),
        b._module("app.domains.sample.models", imports=("app.models",), external=("sqlalchemy",)),
    )
    assert b.checker.check_inventory(inventory, completed_policy()) == []


@pytest.mark.parametrize("name", [
    "app.domains.sample.application.new_flow", "app.domains.sample.domain.rules",
    "app.domains.sample.ports.repository", "app.domains.sample.api.routes",
    "app.domains.sample.infrastructure.repository", "app.domains.sample.public",
    "app.schemas", "app.schemas.sample", "app.services.sample", "app.cruds.sample",
    "app.repositories.sample", "app.models.sample", "app.compatibility.new_flow",
])
def test_unused_new_legacy_file_is_rejected_even_without_an_import_edge(name):
    inventory = b._inventory(b._module("app.domains.sample.service"), b._module(name))
    assert any("refactor_unregistered_old_module" in error for error in
               b.checker.check_inventory(inventory, completed_policy()))


def test_new_domain_must_have_declared_ownership_even_without_cross_domain_imports():
    inventory = b._inventory(
        b._module("app.domains.sample.service"), b._module("app.domains.unknown.service"),
    )
    assert any("refactor_unowned_domain" in error for error in
               b.checker.check_inventory(inventory, completed_policy()))


def test_removed_domain_and_retained_contract_cannot_stay_in_policy():
    policy = completed_policy()
    policy["refactor"]["retained_modules"] = [retained("app.domains.sample.infrastructure.schema")]
    errors = b.checker.check_inventory(b._inventory(), policy)
    assert any("refactor_stale_domain" in error for error in errors)
    assert any("refactor_stale_retained_module" in error for error in errors)


def test_exact_historical_path_is_allowed_but_does_not_open_its_siblings():
    policy = completed_policy()
    name = "app.domains.sample.infrastructure.schema"
    policy["refactor"]["retained_modules"] = [retained(name)]
    base = [b._module("app.domains.sample.service"), b._module(name)]
    assert b.checker.check_inventory(b._inventory(*base), policy) == []
    errors = b.checker.check_inventory(b._inventory(*base, b._module(name + "_new")), policy)
    assert any("refactor_unregistered_old_module" in error for error in errors)


def test_retained_contract_does_not_allow_runtime_import_into_a_domain():
    policy = completed_policy()
    name = "app.domains.sample.infrastructure.schema"
    policy["refactor"]["retained_modules"] = [retained(name)]
    inventory = b._inventory(
        b._module("app.domains.sample.service"),
        b._module(name, imports=("app.runtime.worker",)), b._module("app.runtime.worker"),
    )
    assert any("domain_imports_runtime" in error for error in b.checker.check_inventory(inventory, policy))


@pytest.mark.parametrize("mutation", ["wildcard", "missing_contract", "duplicate", "kind", "complete_type", "partial_scope"])
def test_incomplete_or_broad_final_scope_is_rejected(mutation):
    policy = completed_policy()
    entry = retained("app.domains.sample.infrastructure.schema")
    policy["refactor"]["retained_modules"] = [entry]
    if mutation == "wildcard":
        entry["module"] = "app.domains.sample.infrastructure.*"
    elif mutation == "missing_contract":
        del entry["contract"]
    elif mutation == "duplicate":
        policy["refactor"]["retained_modules"].append(dict(entry))
    elif mutation == "kind":
        entry["kind"] = "temporary_convenience"
    elif mutation == "complete_type":
        policy["refactor"]["complete"] = "true"
    elif mutation == "partial_scope":
        policy["refactor"]["modules"] = ["app.domains.sample.service"]
    assert any("refactor_invalid_scope" in error for error in
               b.checker.check_inventory(b._inventory(), policy))


def test_repository_keeps_complete_backend_policy_enabled():
    policy = json.loads((ROOT / "security/architecture_import_policy.json").read_text(encoding="utf-8"))
    inventory = json.loads((ROOT / "security/architecture_import_baseline.json").read_text(encoding="utf-8"))
    scope = policy["refactor"]
    assert scope["complete"] is True
    assert scope["modules"] == []
    assert set(scope["globals"]) == {"app.config", "app.models", "app.database", "app.exceptions", "app.pagination"}
    assert policy["legacy_exception_groups"] == []
    assert b.checker.check_inventory(inventory, policy) == []


def test_repository_retained_modules_have_readable_contracts():
    policy = json.loads((ROOT / "security/architecture_import_policy.json").read_text(encoding="utf-8"))
    retained = policy["refactor"]["retained_modules"]
    assert retained
    for item in retained:
        contract = (ROOT / item["contract"]).resolve()
        assert contract.is_relative_to(ROOT.resolve())
        assert contract.is_file(), item["module"]
        assert contract.read_text(encoding="utf-8").strip()
