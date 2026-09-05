"""AR-G0: partial migration scopes must not relax unconverted code boundaries."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "partial_scope_fixtures", ROOT / "backend/tests/test_t2_5_architecture_boundaries.py"
)
assert SPEC is not None and SPEC.loader is not None
b = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(b)

SERVICE = "app.domains.memory.service.recall"
SCHEMA = "app.domains.memory.schemas.recall"
OLD = "app.domains.memory.application.recall"


def policy(*, modules=(SERVICE,), entries=(SERVICE,), bridges=()):
    result = b._policy()
    result["refactor"] = {
        "domains": [], "globals": [], "modules": list(modules),
        "entries": list(entries), "bridges": list(bridges),
    }
    return result


def bridge(source=OLD, target=SERVICE):
    return {
        "importer": source, "target": target, "owner_stage": "AR-B7-A",
        "reason": "Retain the old recall import while its consumers migrate.",
        "removal_condition": "Remove after recorded recall consumers use the new service.",
        "review_date": "2026-09-05",
    }


def errors(*modules, scope=None):
    return b.checker.check_inventory(b._inventory(*modules), scope or policy())


def test_partial_service_and_schema_entries_work_without_completing_the_domain():
    result = errors(
        b._module("app.domains.chat.application.reply", imports=(SERVICE, SCHEMA)),
        b._module(SERVICE, imports=(SCHEMA, "app.domains.identity.public")),
        b._module(SCHEMA, external=("pydantic",)),
        b._module("app.domains.identity.public"),
        b._module("app.domains.memory.application.batch"),
        scope=policy(modules=(SERVICE, SCHEMA), entries=(SERVICE, SCHEMA)),
    )
    assert result == []


@pytest.mark.parametrize("target", [
    "app.domains.memory.service.batch",
    "app.domains.memory.repository.items",
    "app.domains.memory.models.items",
    "app.domains.memory.router",
    "app.domains.memory.schemas.internal",
])
def test_cross_domain_consumers_cannot_use_unlisted_siblings_or_storage(target):
    result = errors(
        b._module("app.domains.chat.application.reply", imports=(target,)),
        b._module(SERVICE), b._module(target),
    )
    assert any("cross_domain_deep_import" in error for error in result)


@pytest.mark.parametrize("target", [SERVICE + ".internal", SERVICE])
def test_a_partial_package_does_not_expose_all_descendants_or_private_modules(target):
    partial = "app.domains.memory.service"
    scope = policy(modules=(partial, SERVICE), entries=(partial,))
    fixture = {name: b._module(name) for name in (partial, SERVICE, target)}
    result = errors(
        b._module("app.domains.chat.application.reply", imports=(target,)),
        *fixture.values(), scope=scope,
    )
    assert any("cross_domain_deep_import" in error for error in result)


def test_completed_domain_submodules_need_an_exact_supported_entry():
    scope = policy(modules=(), entries=())
    scope["refactor"]["domains"] = ["memory"]
    fixture = (
        b._module("app.domains.chat.application.reply", imports=(SERVICE,)),
        b._module(SERVICE),
    )
    assert any("cross_domain_deep_import" in error for error in errors(*fixture, scope=scope))
    scope["refactor"]["entries"] = [SERVICE]
    assert errors(*fixture, scope=scope) == []


@pytest.mark.parametrize("field,value", [
    ("modules", ["app.domains.memory"]),
    ("modules", ["app.domains.memory.service.*"]),
    ("modules", ["app.domains.memory.service..recall"]),
    ("modules", [OLD]),
    ("modules", [SERVICE, SERVICE]),
    ("entries", ["app.domains.memory.service.unmigrated"]),
    ("entries", ["app.domains.memory.repository.items"]),
    ("entries", ["app.domains.memory.public"]),
])
def test_scope_cannot_promote_a_domain_or_expose_unmigrated_and_unsafe_entries(field, value):
    scope = policy()
    scope["refactor"][field] = value
    assert any("refactor_invalid_scope" in error for error in errors(b._module(SERVICE), scope=scope))


def test_scope_must_not_mark_a_domain_both_partial_and_complete():
    scope = policy()
    scope["refactor"]["domains"] = ["memory"]
    assert any("refactor_invalid_scope" in error for error in errors(b._module(SERVICE), scope=scope))


def test_nonexistent_migrated_entry_is_not_an_import_allowlist():
    result = errors(b._module("app.domains.chat.application.reply", imports=(SERVICE,)))
    assert any("refactor_stale_scope" in error for error in result)


def test_unconverted_sibling_keeps_legacy_pure_layer_protection():
    result = errors(
        b._module(SERVICE),
        b._module("app.domains.memory.application.batch", external=("sqlalchemy",)),
    )
    assert any("domain_pure_layer_imports_framework" in error for error in result)


def test_unconverted_domain_still_requires_its_old_public_boundary():
    result = errors(
        b._module(SERVICE),
        b._module("app.domains.chat.application.reply", imports=("app.domains.social.service",)),
        b._module("app.domains.social.service"),
    )
    assert any("cross_domain_deep_import" in error for error in result)


def test_partial_implementation_cannot_hide_dependencies_in_unscoped_new_siblings():
    result = errors(
        b._module(SERVICE, imports=("app.domains.memory.service.batch",)),
        b._module("app.domains.memory.service.batch"),
    )
    assert any("refactor_unmigrated_module_dependency" in error for error in result)


def test_old_alias_requires_an_exact_one_way_bridge_and_keeps_old_public_consumers():
    fixture = (
        b._module("app.domains.chat.application.reply", imports=("app.domains.memory.public",)),
        b._module("app.domains.memory.public", imports=(OLD,)),
        b._module(OLD, imports=(SERVICE,)), b._module(SERVICE),
    )
    assert any("refactor_unregistered_legacy_consumer" in error for error in errors(*fixture))
    assert errors(*fixture, scope=policy(bridges=(bridge(),))) == []


def test_bridge_never_allows_a_second_unregistered_old_consumer():
    result = errors(
        b._module(OLD, imports=(SERVICE,)),
        b._module(OLD + "_other", imports=(SERVICE,)),
        b._module(SERVICE), scope=policy(bridges=(bridge(),)),
    )
    assert any("refactor_unregistered_legacy_consumer" in error and OLD + "_other" in error for error in result)


@pytest.mark.parametrize("old", ["app.models.memory", "app.services.memory", "app.core.old_memory"])
def test_exact_old_non_domain_alias_to_migrated_implementation_is_recorded(old):
    # Core still cannot depend on a domain: bridge metadata must not waive that rule.
    result = errors(
        b._module(old, imports=(SERVICE,)), b._module(SERVICE),
        scope=policy(bridges=(bridge(old),)),
    )
    if old.startswith("app.core."):
        assert any("core_dependency_direction" in error for error in result)
    else:
        assert result == []


@pytest.mark.parametrize("old", ["app.models", "app.models.memory", "app.schemas.memory", "app.services.memory", "app.cruds.memory", "app.repositories.memory"])
def test_old_horizontal_layer_consumer_also_requires_a_registered_transition(old):
    result = errors(b._module(old, imports=(SERVICE,)), b._module(SERVICE))
    assert any("refactor_unregistered_legacy_consumer" in error for error in result)


@pytest.mark.parametrize("target", ["app.config", "app.models", "app.exceptions", "app.pagination", "app.database"])
def test_old_business_service_may_consume_approved_shared_globals_without_alias_metadata(target):
    scope = policy(modules=(), entries=())
    scope["refactor"]["globals"] = [target]
    result = errors(
        b._module("app.services.chat_reply", imports=(target,)), b._module(target),
        scope=scope,
    )
    assert result == []


@pytest.mark.parametrize("source,external", [
    ("app.exceptions", "fastapi"),
    ("app.pagination", "sqlalchemy"),
    ("app.pagination", "httpx"),
])
def test_pure_shared_error_and_pagination_modules_cannot_import_framework_or_io(source, external):
    scope = policy(modules=(), entries=())
    scope["refactor"]["globals"] = [source, "app.models"]
    result = errors(
        b._module(source, external=(external,)),
        b._module("app.models", external=("sqlalchemy",)), scope=scope,
    )
    assert any("refactor_pure_imports_framework" in error and source in error for error in result)
    assert not any("refactor_pure_imports_framework" in error and "app.models ->" in error for error in result)


def test_unused_compatibility_bridge_fails_instead_of_becoming_a_future_exception():
    result = errors(b._module(OLD), b._module(SERVICE), scope=policy(bridges=(bridge(),)))
    assert any("refactor_stale_bridge" in error for error in result)


@pytest.mark.parametrize("change", [
    {"importer": "app.domains.memory.application.*"},
    {"target": "app.domains.memory.service.*"},
    {"owner_stage": ""}, {"removal_condition": ""}, {"reason": ""},
    {"review_date": "next week"}, {"extra": "blanket permission"},
])
def test_bridge_rejects_wildcards_missing_ownership_and_unknown_fields(change):
    item = bridge()
    item.update(change)
    result = errors(b._module(OLD, imports=(SERVICE,)), b._module(SERVICE), scope=policy(bridges=(item,)))
    assert any("refactor_invalid_bridge" in error for error in result)


def test_duplicate_bridge_is_rejected():
    result = errors(b._module(OLD, imports=(SERVICE,)), b._module(SERVICE), scope=policy(bridges=(bridge(), bridge())))
    assert any("refactor_invalid_bridge" in error for error in result)


def test_bridge_target_must_be_a_migrated_inventory_module():
    result = errors(
        b._module(OLD, imports=(SCHEMA,)), b._module(SCHEMA), b._module(SERVICE),
        scope=policy(bridges=(bridge(target=SCHEMA),)),
    )
    assert any("refactor_unmigrated_bridge_target" in error for error in result)


def test_new_role_cannot_disguise_itself_as_an_old_compatibility_alias():
    source = "app.domains.memory.service.batch"
    result = errors(
        b._module(source, imports=(SERVICE,)), b._module(SERVICE),
        scope=policy(bridges=(bridge(source),)),
    )
    assert any("refactor_invalid_bridge_source" in error for error in result)


def test_compatibility_does_not_allow_cross_domain_storage_access():
    source = "app.domains.chat.application.reply"
    target = "app.domains.memory.repository.items"
    result = errors(
        b._module(source, imports=(target,)), b._module(target),
        scope=policy(modules=(target,), entries=(), bridges=(bridge(source, target),)),
    )
    assert any("refactor_cross_domain_bridge" in error for error in result)
    assert any("refactor_cross_domain_role" in error for error in result)


def test_reverse_bridge_and_new_module_cycle_are_both_rejected():
    result = errors(
        b._module(OLD, imports=(SERVICE,)), b._module(SERVICE, imports=(OLD,)),
        scope=policy(bridges=(bridge(),)),
    )
    assert any("refactor_reverse_bridge" in error for error in result)
    assert any("refactor_new_imports_legacy" in error for error in result)
    assert any("[module_cycle]" in error for error in result)


def test_migrated_implementation_cannot_import_a_registered_alias_in_another_layer():
    old = "app.compatibility.recall"
    result = errors(
        b._module(old, imports=(SERVICE,)), b._module(SERVICE),
        b._module(SCHEMA, imports=(old,)),
        scope=policy(modules=(SERVICE, SCHEMA), bridges=(bridge(old),)),
    )
    assert any("refactor_new_imports_legacy" in error for error in result)


@pytest.mark.parametrize("imports,external,expected", [
    (("app.domains.memory.router",), (), "refactor_service_imports_http"),
    ((OLD,), (), "refactor_new_imports_legacy"),
    (("app.runtime.memory",), (), "domain_imports_runtime"),
    ((), ("google.generativeai",), "domain_runtime_imports_provider_sdk"),
])
def test_partial_scope_keeps_new_role_and_runtime_provider_rules(imports, external, expected):
    names = {SERVICE, *imports}
    scope_modules = (SERVICE, "app.domains.memory.router") if "app.domains.memory.router" in names else (SERVICE,)
    fixture = [b._module(name, imports=imports if name == SERVICE else (), external=external if name == SERVICE else ()) for name in names]
    assert any(expected in error for error in errors(*fixture, scope=policy(modules=scope_modules)))


def test_partial_policy_has_the_same_pure_role_restriction_as_completed_domains():
    source = "app.domains.memory.policies.retention"
    result = errors(b._module(source, external=("sqlalchemy",)), scope=policy(modules=(source,), entries=()))
    assert any("refactor_pure_imports_framework" in error for error in result)


def test_exact_global_scope_does_not_exempt_old_model_submodules():
    scope = policy()
    scope["refactor"]["globals"] = ["app.models"]
    result = errors(
        b._module(SERVICE, imports=("app.models", "app.models.memory")),
        b._module("app.models"), b._module("app.models.memory"), scope=scope,
    )
    assert any("legacy_edge_not_allowlisted" in error and "app.models.memory" in error for error in result)
    assert not any("legacy_edge_not_allowlisted" in error and " -> app.models;" in error for error in result)


def test_old_allowlisted_cycle_does_not_hide_a_new_partial_module_cycle():
    scope = policy(modules=(SERVICE, SCHEMA))
    scope["legacy_module_cycles"] = [b._cycle("app.legacy_a", "app.legacy_b")]
    result = errors(
        b._module("app.legacy_a", imports=("app.legacy_b",)),
        b._module("app.legacy_b", imports=("app.legacy_a",)),
        b._module(SERVICE, imports=(SCHEMA,)), b._module(SCHEMA, imports=(SERVICE,)),
        scope=scope,
    )
    assert any("[module_cycle]" in error and SERVICE in error for error in result)
    assert not any("[stale_legacy_cycle]" in error for error in result)


def test_cross_domain_cycle_detection_survives_precise_supported_entries():
    caller = "app.domains.chat.service.reply"
    result = errors(
        b._module(SERVICE, imports=(caller,)), b._module(caller, imports=(SERVICE,)),
        scope=policy(modules=(SERVICE, caller), entries=(SERVICE, caller)),
    )
    assert any("[package_cycle]" in error for error in result)
    assert any("[module_cycle]" in error for error in result)
