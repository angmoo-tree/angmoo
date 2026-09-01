"""Generate or verify the append-only P8-L-E profile and Chat-entry inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = ROOT / "docs/architecture/p8-l-e-world-social-chat-entry-inventory.json"
D_INVENTORY_PATH = ROOT / "docs/architecture/p8-l-d-world-chat-identity-inventory.json"
D_INVENTORY_SHA256 = (
    "f0f5c1e1b9bf5ddcbf86f30ccc812ce30597f1a16ca08dd61040eb9610a322a3"
)


class InventoryError(RuntimeError):
    """Stable failure for a missing or drifting P8-L-E invariant."""


def _normalized_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def _sha256(path: Path) -> str:
    return hashlib.sha256(_normalized_bytes(path)).hexdigest()


def _record(relative: str) -> dict[str, Any]:
    path = ROOT / relative
    if not path.is_file():
        raise InventoryError(f"required file is missing: {relative}")
    data = _normalized_bytes(path)
    return {
        "path": relative,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    }


def _require_text(relative: str, values: tuple[str, ...]) -> None:
    text = (ROOT / relative).read_text(encoding="utf-8")
    missing = [value for value in values if value not in text]
    if missing:
        raise InventoryError(f"{relative}: required contract missing: {missing}")


def _backend_contract() -> dict[str, Any]:
    _require_text(
        "backend/app/domains/world_characters/api/routes.py",
        (
            '"/{world_id}/world-characters"',
            '"/{world_id}/world-characters/{world_character_id}"',
            "WorldCharacterProfileRead",
            "WorldCharacterProfileListRead",
        ),
    )
    _require_text(
        "backend/app/api/v1/routes/world_chat.py",
        (
            'prefix="/worlds/{world_id}/world-characters"',
            '"/{responding_id}/chat-entry"',
            "WorldChatEntryRead",
        ),
    )
    for relative in ("backend/app/api/v1/main.py", "backend/app/api/v1/public.py"):
        _require_text(relative, ("world_chat.entry_router", "world_chat.router"))
    _require_text(
        "backend/app/runtime/chat/sqlalchemy_service.py",
        (
            "requester_cardinality=\"zero\"",
            "requester_cardinality=\"one\"",
            "requester_cardinality=\"anomaly\"",
            "disabled_reason=\"self_target\"",
            "disabled_reason=\"blocked\"",
            "create_or_get_world_thread",
        ),
    )
    _require_text(
        "backend/app/runtime/social/sqlalchemy_read_repository.py",
        (
            "author_profile_capability",
            "author_world_character_id",
            "world_character_pair_is_blocked",
        ),
    )
    _require_text(
        "backend/app/api/v1/routes/manual_social.py",
        (
            '"/{world_id}/world-characters/{world_character_id}/social-profile"',
            'Literal["posts", "replies", "likes"]',
            "WorldCharacterSocialProfileRead",
        ),
    )
    _require_text(
        "backend/app/runtime/social/sqlalchemy_profile_repository.py",
        (
            "SqlAlchemyWorldCharacterSocialProfileReader",
            "world-character-social-profile-cursor-v1",
            "received_like_count",
            "_blocked_world_character_ids",
        ),
    )
    return {
        "profile_operations": [
            "GET /worlds/{world_id}/world-characters",
            "GET /worlds/{world_id}/world-characters/{world_character_id}",
        ],
        "chat_entry_operation": (
            "GET /worlds/{world_id}/world-characters/{responding_id}/chat-entry"
        ),
        "create_or_get_operation": "POST /worlds/{world_id}/chat/threads",
        "social_profile_operation": (
            "GET /worlds/{world_id}/world-characters/{world_character_id}/social-profile"
        ),
        "social_profile_contract": {
            "scope": "exact_current_world",
            "tabs": ["posts", "replies", "likes"],
            "counts": [
                "post_count",
                "reply_count",
                "liked_post_count",
                "received_like_count",
            ],
            "cursor": "opaque_world_character_tab_scoped",
            "visibility": "active_unblocked_visible_only",
        },
        "requester_cardinality": ["zero", "one", "anomaly"],
        "fail_closed_reasons": [
            "requester_missing",
            "requester_cardinality_anomaly",
            "self_target",
            "blocked",
            "target_not_chat_capable",
        ],
    }


def _frontend_contract() -> dict[str, Any]:
    _require_text(
        "frontend/src/features/characters/public.ts",
        (
            "getWorldCharacterProfile",
            "listWorldCharacterProfiles",
            "WorldCharacterDirectory",
            "WorldCharacterProfile",
        ),
    )
    _require_text(
        "frontend/src/features/chat/public.ts",
        ("getWorldChatEntry", "createOrGetWorldChatThread", "WorldChatEntryRead"),
    )
    _require_text(
        "frontend/src/features/social/ui/world-social-feed.tsx",
        ("author_profile_capability", "worldCharacterProfileRoute"),
    )
    _require_text(
        "frontend/src/features/social/ui/social-post-row.tsx",
        (
            "authorHref",
            'data-post-card-ignore',
            "게시글 자세히 보기",
            "프로필 열기",
        ),
    )
    _require_text(
        "frontend/src/features/characters/ui/world-character-profile.tsx",
        (
            "chatStartInFlightRef",
            "requester_cardinality_anomaly",
            "requester_missing",
            "self_target",
            "blocked",
            "worldChatThreadRoute",
            "WorldCharacterSocialProfileActivity",
            "useRuntimeBack",
            "data-world-character-directory-icon",
        ),
    )
    _require_text(
        "frontend/src/features/social/public.ts",
        (
            "getWorldCharacterSocialProfile",
            "WorldCharacterSocialProfileActivity",
            "WorldCharacterSocialProfileTab",
        ),
    )
    _require_text(
        "frontend/src/shared/ui/device-frame.module.css",
        ("scrollbar-gutter: auto", "scrollbar-width: none", "::-webkit-scrollbar"),
    )
    _require_text(
        "frontend/src/shared/desktop/product-window.ts",
        (
            "DESKTOP_ROUTE_HISTORY_INDEX",
            "synchronizeDesktopRouteFromBrowserHistory",
            "navigateBackCurrentDesktopRoute",
        ),
    )
    _require_text(
        "frontend/src/shared/navigation/product-routes.ts",
        ("worldCharacterProfileRoute", "worldCharacterDirectoryRoute"),
    )
    _require_text(
        "frontend/src/composition/static-product-router.tsx",
        ('segments[2] === "characters"', "worldCharacterId"),
    )
    _require_text(
        "desktop/src-tauri/src/product_windows.rs",
        (
            '"characters", world_character_id',
            "/worlds/world-1/characters/world-character-1",
        ),
    )
    return {
        "profile_route": "/worlds/{worldId}/characters/{worldCharacterId}",
        "route_parity": ["next", "static", "tauri"],
        "feature_owners": {
            "profile": "features/characters",
            "letter_and_thread_entry": "features/chat",
            "social_author_link": "features/social",
        },
        "interaction_boundaries": [
            "post_card_to_post_detail",
            "author_avatar_to_profile",
            "author_name_to_profile",
        ],
        "thread_entry": "idempotent_create_or_get",
        "profile_activity": {
            "feature_owner": "features/social",
            "scope": "exact_current_world",
            "metrics": 4,
            "tabs": 3,
            "owner_actions": 0,
        },
        "phone_presentation": {
            "scrolling": "preserved",
            "visible_scrollbar": "hidden",
            "reserved_scrollbar_gutter": "removed",
            "directory_icon_alignment": "centered",
        },
        "profile_back_navigation": {
            "tauri_popstate_store_sync": True,
            "direct_entry_fallback": "/worlds/{worldId}/characters",
        },
    }


def build_inventory() -> dict[str, Any]:
    if _sha256(D_INVENTORY_PATH) != D_INVENTORY_SHA256:
        raise InventoryError("frozen P8-L-D inventory digest drift")
    return {
        "schema_version": 2,
        "owner_stage": "P8-L-E",
        "predecessor": _record(
            "docs/architecture/p8-l-d-world-chat-identity-inventory.json"
        ),
        "historical_chain": {
            "p8_l_d_sha256": D_INVENTORY_SHA256,
            "predecessor_mode": "frozen_digest",
            "current_tree_owner": "P8-L-E",
        },
        "backend": _backend_contract(),
        "frontend": _frontend_contract(),
        "non_scope": [
            "message_send",
            "response_generation",
            "streaming",
            "retrieval",
            "memory_write",
        ],
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
                "P8-L-E inventory drift; run python "
                "scripts/ci/generate_p8_l_e_world_social_chat_entry_inventory.py --write"
            )
        print("P8-L-E World social Chat-entry inventory is current")
        return 0
    except (InventoryError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(f"P8-L-E inventory check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
