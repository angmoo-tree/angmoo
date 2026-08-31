from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8").replace("\r\n", "\n")


def test_world_chat_contract_transport_and_public_boundary_are_feature_owned() -> None:
    public = _read("frontend/src/features/chat/public.ts")
    contract = _read(
        "frontend/src/features/chat/model/world-chat-contract.ts"
    )
    client = _read("frontend/src/features/chat/api/world-chat-client.ts")

    for marker in (
        "WorldChatRoleRead",
        "WorldChatThreadRead",
        "WorldChatThreadListRead",
        "WorldChatThreadCreateRead",
        "resolvedLegacyWorldChatRouteParts",
        'export { WorldChat } from "./ui/world-chat";',
    ):
        assert marker in public or marker in contract
    for marker in (
        "listWorldChatThreads",
        "getWorldChatThread",
        "createOrGetWorldChatThread",
        '`/worlds/${encodeURIComponent(worldId)}/chat${suffix}`',
        'method: "POST"',
        'credentials: "same-origin"',
        'thread.requester.control_mode !== "owner_controlled"',
        'thread.requester.world_character_id === thread.responding.world_character_id',
        'message.thread_id === thread.id',
        'WorldChatApiError(502, "world_chat_scope_mismatch")',
    ):
        assert marker in client
    assert "/messages/" not in client
    assert "SQL" not in client
    assert "Cypher" not in client


def test_canonical_world_chat_route_is_shared_by_next_static_and_tauri_phone() -> None:
    page = _read(
        "frontend/src/app/worlds/[worldId]/chat/[threadId]/page.tsx"
    )
    route_client = _read("frontend/src/app/world-app-route-client.tsx")
    static_router = _read("frontend/src/composition/static-product-router.tsx")
    product_routes = _read("frontend/src/shared/navigation/product-routes.ts")
    capability = _read(
        "frontend/src/features/device-shell/model/device-navigation.ts"
    )
    safe_navigation = _read("frontend/src/lib/safe-navigation.ts")
    rust = _read("desktop/src-tauri/src/product_windows.rs")

    assert 'sectionId="chat"' in page
    assert "chatThreadId={threadId}" in page
    assert "await params" in page
    assert "WorldAppRouteClient" in page
    assert "chatThreadId?: string" in route_client
    assert 'segments[2] === "chat"' in static_router
    assert 'segments.length === 4' in static_router
    assert static_router.index('segments[2] === "chat"') < static_router.index(
        "segments.length >= 2 && segments.length <= 3"
    )
    assert "export function worldChatRoute" in product_routes
    assert "export function worldChatThreadRoute" in product_routes
    assert 'routeFamily: "/worlds/{worldId}/chat/{threadId}"' in capability
    assert "/chat\\/[^/]+$/" in capability
    assert '"chat", thread_id' in rust
    assert '"/worlds/world-1/chat/thread-1"' in rust
    assert "chat(?:\\/[^/?#]+)?" in safe_navigation


def test_world_chat_ui_is_read_only_scoped_and_semantic_in_p8_l_d() -> None:
    world_app = _read("frontend/src/features/world-app/ui/world-app.tsx")
    world_contract = _read(
        "frontend/src/features/world-app/model/world-app-contract.ts"
    )
    ui = _read("frontend/src/features/chat/ui/world-chat.tsx")
    css = _read("frontend/src/features/chat/ui/world-chat.module.css")

    assert 'availability: "available"' in world_contract
    assert 'activeSection.id === "chat"' in world_app
    assert "<WorldChat threadId={chatThreadId} worldId={worldId} />" in world_app
    for marker in (
        'data-world-chat-surface="list"',
        'data-world-chat-surface="thread"',
        "thread.requester.display_name",
        "thread.responding.display_name",
        "말하는 앵무",
        "답하는 앵무",
        "World 경계를 확인했어요",
        "다른 World의 응답은 표시하지 않았습니다.",
    ):
        assert marker in ui
    for forbidden in (
        "sendThreadMessage",
        "retryThreadMessage",
        "Character Response Generator",
        "입력 중",
        "<textarea",
        "onSubmit",
    ):
        assert forbidden not in ui
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css)
    assert "rgb(" not in css
    assert "var(--color-" in css


def test_legacy_messages_redirect_only_resolved_scope_and_name_other_states() -> None:
    contract = _read("frontend/src/features/chat/model/chat-contract.ts")
    helper = _read(
        "frontend/src/features/chat/model/world-chat-contract.ts"
    )
    listing = _read("frontend/src/features/chat/ui/messages-client.tsx")
    thread = _read(
        "frontend/src/features/chat/ui/message-thread-client.tsx"
    )

    assert '"resolved" | "ambiguous" | "quarantined"' in contract
    assert 'thread.world_scope_status !== "resolved"' in helper
    for required_identity in (
        "thread.world_id",
        "thread.requester_world_character_id",
        "thread.responding_world_character_id",
    ):
        assert required_identity in helper
    assert "worldChatThreadRoute(resolved.worldId, resolved.threadId)" in listing
    assert "worldChatThreadRoute(resolved.worldId, resolved.threadId)" in thread
    assert 'thread.world_scope_status === "quarantined"' in listing
    assert 'thread.world_scope_status === "quarantined"' in thread
    assert "충돌 대화 격리됨" in listing
    assert "임의의 World로 연결하지 않습니다." in thread
