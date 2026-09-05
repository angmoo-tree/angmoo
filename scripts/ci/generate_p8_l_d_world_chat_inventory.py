"""Generate or verify the append-only P8-L-D World Chat identity inventory."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = ROOT / "docs/architecture/p8-l-d-world-chat-identity-inventory.json"
B_INVENTORY_PATH = ROOT / "security/p8_l_b_chat_domain_inventory.json"
A_INVENTORY_PATH = ROOT / "security/p8_l_a_inventory.json"
A_INVENTORY_SHA256 = (
    "934c1410810e8f0b0899e09c3c34b5c67f43050c4a354a15fcea72f264c9847e"
)
B_INVENTORY_SHA256 = (
    "d9e5b83d78059d91629f001e48d3031bd44a495f625be1588f00770395c5d70e"
)

IMMUTABLE_D_FILES = (
    "backend/app/alembic/versions/20260831_0084_world_scoped_chat_identity.py",
    "backend/app/domains/chat/infrastructure/world_scope_migration.py",
    "backend/app/runtime/migrations/sqlite_versions/v3_to_v4_world_scoped_chat.py",
    "backend/app/runtime/migrations/sqlite_versions/manifests/v4.json",
)
# The historical inventory keeps its recorded path and content digest. Read
# the same immutable revision from its current physical location after AR-G4.
ALEMBIC_REVISION_SOURCE = "backend/alembic/versions/20260831_0084_world_scoped_chat_identity.py"
REQUIRED_THREAD_COLUMNS = (
    "world_id",
    "requester_world_character_id",
    "responding_world_character_id",
    "world_scope_status",
)
REQUIRED_THREAD_CONSTRAINTS = (
    "ck_message_threads_world_scope_binding",
    "fk_message_threads_world",
    "fk_message_threads_requester_world",
    "fk_message_threads_responding_world",
    "fk_message_threads_responding_character",
)
REQUIRED_THREAD_INDEXES = (
    "ix_message_threads_owner_world_status",
    "uq_message_threads_active_legacy_ambiguous",
    "uq_message_threads_active_world_roles",
)
REQUIRED_ROUTE_OPERATIONS = (
    "GET /worlds/{world_id}/chat/threads",
    "GET /worlds/{world_id}/chat/threads/{thread_id}",
    "POST /worlds/{world_id}/chat/threads",
)
ALLOWED_LATER_ROUTE_OPERATIONS = (
    "PATCH /worlds/{world_id}/chat/threads/{thread_id}/model",
)


class InventoryError(RuntimeError):
    """Stable failure for a missing or drifting P8-L-D invariant."""


def _normalized_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def _sha256(path: Path) -> str:
    return hashlib.sha256(_normalized_bytes(path)).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise InventoryError(f"{path}: root must be an object")
    return value


def _record(relative: str) -> dict[str, Any]:
    path = ROOT / (ALEMBIC_REVISION_SOURCE if relative == IMMUTABLE_D_FILES[0] else relative)
    if not path.is_file():
        raise InventoryError(f"required file is missing: {relative}")
    data = _normalized_bytes(path)
    return {
        "path": relative,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    }


def _assignment(tree: ast.Module, name: str) -> Any:
    for node in tree.body:
        target: ast.expr | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        if isinstance(target, ast.Name) and target.id == name and value is not None:
            try:
                return ast.literal_eval(value)
            except (TypeError, ValueError):
                return None
    return None


def _require_text(relative: str, values: tuple[str, ...]) -> None:
    text = (ROOT / relative).read_text(encoding="utf-8")
    missing = [value for value in values if value not in text]
    if missing:
        raise InventoryError(f"{relative}: required contract missing: {missing}")


def _route_operations() -> tuple[str, ...]:
    path = ROOT / "backend/app/api/v1/routes/world_chat.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    prefix = None
    operations: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "router"
            for target in node.targets
        ):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        for keyword in node.value.keywords:
            if (
                keyword.arg == "prefix"
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, str)
            ):
                prefix = keyword.value.value
    if not isinstance(prefix, str):
        raise InventoryError("World Chat router prefix is missing")
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not decorator.args:
                continue
            func = decorator.func
            if not (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "router"
                and func.attr in {"get", "post", "patch", "delete"}
                and isinstance(decorator.args[0], ast.Constant)
                and isinstance(decorator.args[0].value, str)
            ):
                continue
            operations.add(
                f"{func.attr.upper()} {prefix}{decorator.args[0].value}"
            )
    return tuple(sorted(operations))


def _migration_contract() -> dict[str, Any]:
    alembic_path = ROOT / ALEMBIC_REVISION_SOURCE
    alembic_tree = ast.parse(
        alembic_path.read_text(encoding="utf-8"), filename=str(alembic_path)
    )
    revision = _assignment(alembic_tree, "revision")
    down_revision = _assignment(alembic_tree, "down_revision")
    if revision != "20260831_0084" or down_revision != "20260825_0083":
        raise InventoryError("P8-L-D Alembic lineage drift")

    embedded = _json(ROOT / IMMUTABLE_D_FILES[3])
    expected = {
        "schema_version": 4,
        "source_revision": "20260831_0084",
        "source_migration_count": 83,
        "canonical_table_count": 87,
    }
    actual = {key: embedded.get(key) for key in expected}
    if actual != expected or len(str(embedded.get("schema_digest") or "")) != 64:
        raise InventoryError(f"embedded SQLite v4 manifest drift: {actual!r}")

    registry = (
        ROOT / "backend/app/runtime/migrations/sqlite_versions/registry.py"
    ).read_text(encoding="utf-8")
    for required in (
        "3: upgrade_v3_to_v4",
        "source_version=3",
        "target_version=4",
        'name="world_scoped_chat"',
    ):
        if required not in registry:
            raise InventoryError(f"embedded v3-to-v4 registry drift: {required}")
    return {
        "alembic_revision": revision,
        "alembic_down_revision": down_revision,
        "embedded_sqlite": {
            **actual,
            "schema_digest": embedded["schema_digest"],
        },
        "mutable_identity_tables": ["message_threads"],
        "migration_registry_step": "v3_to_v4_world_scoped_chat",
    }


def _thread_contract() -> dict[str, Any]:
    relative = "backend/app/domains/chat/infrastructure/sqlalchemy_models.py"
    _require_text(
        relative,
        (*REQUIRED_THREAD_COLUMNS, *REQUIRED_THREAD_CONSTRAINTS, *REQUIRED_THREAD_INDEXES),
    )
    helper = (
        ROOT / "backend/app/domains/chat/infrastructure/world_scope_migration.py"
    ).read_text(encoding="utf-8")
    for required in (
        "len(pairings) != 1",
        "requester_id == responding_id",
        "quarantine_ids",
        "world_scope_status = 'resolved'",
        "cannot_downgrade_world_chat_duplicate_legacy_active_tuple",
    ):
        if required not in helper:
            raise InventoryError(f"World Chat migration invariant drift: {required}")
    return {
        "table": "message_threads",
        "added_columns": list(REQUIRED_THREAD_COLUMNS),
        "required_constraints": list(REQUIRED_THREAD_CONSTRAINTS),
        "required_indexes": list(REQUIRED_THREAD_INDEXES),
        "backfill_outcomes": ["resolved", "ambiguous", "quarantined"],
        "legacy_columns_preserved": True,
        "collision_rows_quarantined": True,
        "lossless_messages_required": True,
    }


def _transport_contract() -> dict[str, Any]:
    operations = _route_operations()
    missing = sorted(set(REQUIRED_ROUTE_OPERATIONS) - set(operations))
    unexpected = sorted(
        set(operations)
        - set(REQUIRED_ROUTE_OPERATIONS)
        - set(ALLOWED_LATER_ROUTE_OPERATIONS)
    )
    if missing or unexpected:
        raise InventoryError(
            f"World Chat route operations drift: missing={missing!r} "
            f"unexpected={unexpected!r}"
        )
    for relative in (
        "backend/app/api/v1/main.py",
        "backend/app/api/v1/public.py",
    ):
        _require_text(relative, ("world_chat.router",))
    _require_text(
        "frontend/src/features/chat/model/world-chat-contract.ts",
        (
            "WorldChatThreadRead",
            "WorldChatThreadCreate",
            "resolvedLegacyWorldChatRouteParts",
        ),
    )
    _require_text(
        "frontend/src/features/chat/api/world-chat-client.ts",
        (
            "listWorldChatThreads",
            "getWorldChatThread",
            "createOrGetWorldChatThread",
            "world_chat_scope_mismatch",
        ),
    )
    _require_text(
        "frontend/src/lib/navigation/product-routes.ts",
        ("worldChatRoute", "worldChatThreadRoute"),
    )
    return {
        "route_operations": list(REQUIRED_ROUTE_OPERATIONS),
        "registered_runtime_routers": ["main", "public"],
        "frontend_contract": "world-scoped",
        "legacy_ambiguous_route_resolution": "explicit-only",
    }


def _installer_contract() -> dict[str, Any]:
    builder_path = ROOT / "scripts/ci/build_windows_installer_supported_upgrade_fixture.py"
    builder_tree = ast.parse(
        builder_path.read_text(encoding="utf-8"), filename=str(builder_path)
    )
    supported = _assignment(builder_tree, "SUPPORTED_SOURCE_VERSIONS")
    if not isinstance(supported, tuple) or 3 not in supported:
        raise InventoryError("installer v3 supported predecessor fixture is missing")
    _require_text(
        "scripts/ci/build_windows_installer_supported_upgrade_fixture.py",
        (
            "rebuild_message_threads_v3",
            "expected_world_chat_threads",
            "thread-supported-world-resolved",
            "thread-supported-world-ambiguous",
        ),
    )
    _require_text(
        "scripts/ci/verify_windows_installer_supported_upgrade_fixture.py",
        (
            "_verify_world_chat_identity",
            "supported_upgrade_world_chat_identity_mismatch",
            "supported_upgrade_world_chat_messages_changed",
        ),
    )
    _require_text(
        "scripts/ci/run_windows_installer_supported_upgrade.ps1",
        ("SupportedV3FixtureArchive", "v3 -> v4"),
    )
    _require_text(
        ".github/workflows/windows-installer.yml",
        (
            "--source-version 3",
            "supported-v3.zip",
            "-SupportedV3FixtureArchive",
        ),
    )
    return {
        "required_predecessor": 3,
        "supported_predecessor_present": True,
        "synthetic_fixture_has_resolved_and_ambiguous_threads": True,
        "message_survival_verified": True,
        "hosted_workflow_archive": "supported-v3.zip",
        "idempotent_target_reinstall_verified": True,
    }


def build_inventory() -> dict[str, Any]:
    if _sha256(A_INVENTORY_PATH) != A_INVENTORY_SHA256:
        raise InventoryError("frozen P8-L-A inventory digest drift")
    if _sha256(B_INVENTORY_PATH) != B_INVENTORY_SHA256:
        raise InventoryError("frozen P8-L-B inventory digest drift")
    return {
        "schema_version": 1,
        "owner_stage": "P8-L-D",
        "predecessor": _record("security/p8_l_b_chat_domain_inventory.json"),
        "historical_chain": {
            "p8_l_a_sha256": A_INVENTORY_SHA256,
            "p8_l_b_sha256": B_INVENTORY_SHA256,
            "predecessor_mode": "frozen_digest",
            "current_tree_owner": "P8-L-D",
        },
        "immutable_files": [_record(relative) for relative in IMMUTABLE_D_FILES],
        "migration": _migration_contract(),
        "message_thread": _thread_contract(),
        "transport": _transport_contract(),
        "installer_upgrade": _installer_contract(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        inventory = build_inventory()
        rendered = json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.write:
            OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT_PATH.write_text(rendered, encoding="utf-8", newline="\n")
            print(f"wrote {OUTPUT_PATH.relative_to(ROOT).as_posix()}")
            return 0
        if not OUTPUT_PATH.is_file():
            raise InventoryError(
                f"generated inventory is missing: {OUTPUT_PATH.relative_to(ROOT)}"
            )
        current = OUTPUT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
        if current != rendered:
            raise InventoryError(
                "P8-L-D inventory drift; run "
                "python scripts/ci/generate_p8_l_d_world_chat_inventory.py --write"
            )
        print("P8-L-D World Chat identity inventory is current")
        return 0
    except (InventoryError, KeyError, OSError, SyntaxError, json.JSONDecodeError) as exc:
        print(f"P8-L-D inventory check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
