from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


b = load("refactor_backend_fixtures", ROOT / "backend/tests/test_t2_5_architecture_boundaries.py")
f = load("refactor_frontend_fixtures", ROOT / "backend/tests/test_l2_5_frontend_architecture_boundaries.py")
p = load("refactor_preservation", ROOT / "scripts/ci/check_refactor_preservation.py")


@pytest.mark.parametrize("role", ["service", "schemas", "contracts"])
def test_flat_supported_entry_and_future_common_base_are_allowed(role):
    policy = b._policy()
    policy["refactor"] = {"domains": ["new_domain"], "globals": ["app.models"]}
    inventory = b._inventory(
        b._module("app.domains.caller.application.run", imports=(f"app.domains.new_domain.{role}",)),
        b._module(f"app.domains.new_domain.{role}"),
        b._module("app.domains.new_domain.models", imports=("app.models",), external=("sqlalchemy",)),
        b._module("app.models", external=("sqlalchemy",)),
    )
    assert b.checker.check_inventory(inventory, policy) == []


@pytest.mark.parametrize("role", ["models", "repository", "router", "public"])
def test_flat_domain_cannot_be_called_through_storage_or_http(role):
    policy = b._policy()
    policy["refactor"] = {"domains": ["new_domain"]}
    inventory = b._inventory(
        b._module("app.domains.caller.application.run", imports=(f"app.domains.new_domain.{role}",)),
        b._module(f"app.domains.new_domain.{role}"),
    )
    assert any("refactor_cross_domain_role" in error for error in b.checker.check_inventory(inventory, policy))


def test_flat_support_does_not_relax_unmigrated_domains():
    policy = b._policy()
    policy["refactor"] = {"domains": ["new_domain"]}
    inventory = b._inventory(b._module("app.domains.caller.service", imports=("app.domains.old.service",)), b._module("app.domains.old.service"))
    assert any("cross_domain_deep_import" in error for error in b.checker.check_inventory(inventory, policy))


@pytest.mark.parametrize("source,target,external,expected", [
    ("app.models", "app.domains.new_domain.models", (), "refactor_common_imports_application"),
    ("app.domains.new_domain.service", "app.domains.new_domain.public", (), "refactor_new_imports_legacy"),
    ("app.domains.new_domain.policies", "app.core.db", (), "refactor_pure_imports_io"),
    ("app.domains.new_domain.policies", "app.models", (), "refactor_pure_imports_io"),
    ("app.domains.new_domain.policies", None, ("sqlalchemy",), "refactor_pure_imports_framework"),
])
def test_flat_role_and_common_reverse_dependencies_are_rejected(source, target, external, expected):
    policy = b._policy()
    policy["refactor"] = {"domains": ["new_domain"], "globals": ["app.models"]}
    modules = [b._module(source, imports=(target,) if target else (), external=external)]
    if target:
        modules.append(b._module(target))
    assert any(expected in error for error in b.checker.check_inventory(b._inventory(*modules), policy))


def test_flat_module_cycles_remain_rejected():
    policy = b._policy()
    policy["refactor"] = {"domains": ["new_domain"]}
    inventory = b._inventory(b._module("app.domains.new_domain.service", imports=("app.domains.new_domain.repository",)), b._module("app.domains.new_domain.repository", imports=("app.domains.new_domain.service",)))
    assert any("module_cycle" in error for error in b.checker.check_inventory(inventory, policy))


def frontend_policy():
    policy = f._policy()
    policy["feature_names"] = sorted(policy["feature_names"] + ["new-feature"])
    policy["refactor"] = {"features": ["new-feature"], "common": ["components/ui/button"], "bridges": []}
    return policy


@pytest.mark.parametrize("statement", [
    'import type { X } from "@/features/device-home/public";',
    'import type { X } from "../../device-home/public.ts";',
    'export { X } from "../../device-home/public";',
    'const p = import("../../device-home/public");',
    'import type { X } from "@/features/device-home";',
])
def test_migrated_feature_cannot_use_other_feature_even_types_or_relative(tmp_path, statement):
    f._write(tmp_path, "frontend/src/features/new-feature/components/card.tsx", statement)
    assert any("refactor_cross_feature" in error for error in f.checker.check_frontend(tmp_path / "frontend/src", frontend_policy()))


@pytest.mark.parametrize("source,target,rule", [
    ("features/new-feature/components/card.tsx", "@/composition/screens/home", "refactor_feature_imports_composition"),
    ("features/new-feature/components/card.tsx", "@/shared/ui/button", "refactor_new_imports_legacy"),
    ("components/ui/button.tsx", "@/features/new-feature/components/card", "refactor_common_imports_application"),
    ("features/new-feature/components/card.tsx", "@/testing/setup-tests", "refactor_production_imports_test"),
    ("components/ui/button.tsx", "./button.test", "refactor_production_imports_test"),
])
def test_frontend_reverse_and_test_dependencies_are_rejected(tmp_path, source, target, rule):
    f._write(tmp_path, "frontend/src/" + source, f'import "{target}";')
    assert any(rule in error for error in f.checker.check_frontend(tmp_path / "frontend/src", frontend_policy()))


def test_app_and_composition_can_import_migrated_feature_actual_files(tmp_path):
    f._write(tmp_path, "frontend/src/app/page.tsx", 'import { Home } from "@/features/new-feature/components/home";')
    f._write(tmp_path, "frontend/src/composition/screens/home.tsx", 'import { Home } from "../../features/new-feature/components/home";')
    f._write(tmp_path, "frontend/src/features/new-feature/components/home.tsx", 'import { Button } from "@/components/ui/button";')
    assert f.checker.check_frontend(tmp_path / "frontend/src", frontend_policy()) == []


def test_exact_bridge_allows_only_the_old_to_new_edge_and_must_be_used(tmp_path):
    policy = frontend_policy()
    policy["refactor"]["bridges"] = [{"importer": "shared/ui/button", "target": "components/ui/button", "owner_stage": "AR-F4", "removal_condition": "All shared consumers moved"}]
    f._write(tmp_path, "frontend/src/shared/ui/button.tsx", 'export { Button } from "@/components/ui/button";')
    assert f.checker.check_frontend(tmp_path / "frontend/src", policy) == []
    f._write(tmp_path, "frontend/src/shared/ui/other.tsx", 'export { Button } from "@/components/ui/button";')
    assert any("shared_imports_product_layer" in error for error in f.checker.check_frontend(tmp_path / "frontend/src", policy))
    (tmp_path / "frontend/src/shared/ui/button.tsx").unlink()
    assert any("refactor_stale_bridge" in error for error in f.checker.check_frontend(tmp_path / "frontend/src", policy))


def test_frozen_nodes_accept_explicit_rename_but_not_loss_or_many_to_one():
    assert p.missing_nodes(["old::one"], ["new::one", "new::extra"], {"old::one": "new::one"}) == []
    assert p.missing_nodes(["old::one"], [], {"old::one": "new::one"}) == ["new::one"]
    with pytest.raises(ValueError, match="one-to-one"):
        p.missing_nodes(["a", "b"], ["c"], {"a": "c", "b": "c"})


def test_scope_cannot_be_expanded_with_wildcards_or_legacy_globals(tmp_path):
    policy = frontend_policy()
    policy["refactor"]["common"] = ["components/*"]
    assert any("refactor_invalid_scope" in error for error in f.checker.check_frontend(tmp_path / "frontend/src", policy))
    policy = b._policy()
    policy["refactor"] = {"globals": ["app.services"]}
    assert any("refactor_invalid_scope" in error for error in b.checker.check_inventory(b._inventory(), policy))


def test_directory_import_cannot_hide_test_support(tmp_path):
    f._write(tmp_path, "frontend/src/features/new-feature/components/card.tsx", 'import { x } from "@/testing";')
    f._write(tmp_path, "frontend/src/testing/index.ts", "export const x = 1;")
    assert any("refactor_production_imports_test" in error for error in f.checker.check_frontend(tmp_path / "frontend/src", frontend_policy()))


def test_migrated_common_cannot_add_a_module_cycle(tmp_path):
    policy = frontend_policy()
    policy["refactor"]["common"].append("components/ui/icon")
    f._write(tmp_path, "frontend/src/components/ui/button.tsx", 'import { Icon } from "./icon";')
    f._write(tmp_path, "frontend/src/components/ui/icon.tsx", 'import { Button } from "./button";')
    assert any("refactor_module_cycle" in error for error in f.checker.check_frontend(tmp_path / "frontend/src", policy))


def test_unmigrated_feature_needs_an_exact_incoming_compatibility_edge(tmp_path):
    policy = frontend_policy()
    f._write(tmp_path, "frontend/src/features/device-home/ui/home.tsx", 'import type { X } from "@/features/new-feature/public";')
    assert any("refactor_unregistered_legacy_consumer" in error for error in f.checker.check_frontend(tmp_path / "frontend/src", policy))
    policy["refactor"]["bridges"] = [{"importer": "features/device-home/ui/home", "target": "features/new-feature/public", "owner_stage": "AR-F2", "removal_condition": "Move this existing API/type consumer to composition"}]
    assert f.checker.check_frontend(tmp_path / "frontend/src", policy) == []


def test_new_composition_uses_actual_feature_file_not_legacy_public(tmp_path):
    f._write(tmp_path, "frontend/src/composition/screens/home.tsx", 'import { X } from "@/features/new-feature/public";')
    assert any("refactor_composition_imports_legacy_entry" in error for error in f.checker.check_frontend(tmp_path / "frontend/src", frontend_policy()))
