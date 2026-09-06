from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8").replace("\r\n", "\n")


def test_message_routes_use_only_the_chat_public_feature_boundary() -> None:
    routes = {
        "frontend/src/app/messages/page.tsx": "MessagesClient",
        "frontend/src/app/messages/[threadId]/page.tsx": "MessageThreadClient",
    }
    for relative, component in routes.items():
        text = _read(relative)
        target = "messages-client" if component == "MessagesClient" else "message-thread-client"
        assert f'from "@/features/chat/components/{target}"' in text
        assert "@/components/messages-client" not in text
        assert "@/components/message-thread-client" not in text
        assert 'dynamic = "force-dynamic"' in text
        assert "NO_INDEX_ROBOTS" in text
        # Historical public-entry topology, after checking current exposure above.
        text = subprocess.check_output(["git", "show", f"d54cbfae8d33084a9b87655d9a9008ff3db3ec0a:{relative}"], cwd=ROOT, text=True, encoding="utf-8")
        assert f'import {{ {component} }} from "@/features/chat/public";' in text
        assert "@/features/chat/" not in text.replace("@/features/chat/public", "")


def test_chat_feature_has_no_legacy_component_or_lib_imports() -> None:
    feature_root = ROOT / "frontend/src/features/chat"
    # Current ownership/common imports are checked by the activated whole feature policy.
    subprocess.run([sys.executable, "scripts/ci/check_frontend_architecture_boundaries.py"], cwd=ROOT, check=True)
    assert (feature_root / "components/world-chat.tsx").is_file()
    assert (feature_root / "types/chat-contract.ts").is_file()
    # Preserve the original P8-L-C topology evidence against its real Git snapshot.
    historical_paths = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "d54cbfae8d33084a9b87655d9a9008ff3db3ec0a", "--", "frontend/src/features/chat"], cwd=ROOT, text=True).splitlines()
    files = [ROOT / relative for relative in historical_paths if Path(relative).suffix in {".ts", ".tsx"}]
    # P8-L-C freezes the five migrated Chat v1 files as a required subset.
    # Later product stages add new feature-owned files without rewriting that
    # historical inventory, so this must not assert an exact directory list.
    assert {
        path.relative_to(feature_root).as_posix() for path in files
    }.issuperset({
        "api/chat-client.ts",
        "model/chat-contract.ts",
        "public.ts",
        "ui/message-thread-client.tsx",
        "ui/messages-client.tsx",
    })
    for path in files:
        text = subprocess.check_output(["git", "show", "d54cbfae8d33084a9b87655d9a9008ff3db3ec0a:" + path.relative_to(ROOT).as_posix()], cwd=ROOT, text=True, encoding="utf-8")
        assert 'from "@/components' not in text
        assert 'from "@/lib' not in text


def test_legacy_chat_frontend_paths_are_thin_compatibility_facades() -> None:
    assert _read("frontend/src/components/messages-client.tsx").strip() == (
        'export { MessagesClient } from "@/features/chat/public";'
    )
    assert _read("frontend/src/components/message-thread-client.tsx").strip() == (
        'export { MessageThreadClient } from "@/features/chat/public";'
    )
    agents = _read("frontend/src/lib/agents.ts")
    assert agents.count('from "@/features/chat/public";') == 2
    for legacy_definition in (
        "export function listMessageThreads",
        "export function sendThreadMessage",
        "export type MessageThreadRead =",
        "export const MESSAGE_GOOGLE_GEMINI_MODELS =",
    ):
        assert legacy_definition not in agents


def test_chat_v1_client_keeps_the_eleven_operation_transport_contract() -> None:
    client = _read("frontend/src/features/chat/api/chat-client.ts")
    assert len(re.findall(r"^export function ", client, flags=re.MULTILINE)) == 11
    assert client.count('method: "POST"') == 3
    assert client.count('method: "PATCH"') == 3
    assert client.count('method: "DELETE"') == 1
    for marker in (
        'requestChatApi<MessageThreadListRead>("/messages/threads")',
        'requestChatApi<MessageThreadRead>("/messages/threads",',
        '"/messages/threads/" + threadId',
        '"/messages/threads/" + threadId + "/messages"',
        '"/messages/threads/" + threadId + "/messages/" + messageId + "/retry"',
        'requestChatApi<MessageSettingsRead>("/messages/settings")',
        'requestChatApi<MessageSettingsRead>("/messages/settings",',
        '"/characters/" + characterId + "/message-settings"',
        'credentials: "same-origin"',
        "clearStoredUser();",
        "notifyAuthChanged();",
        "요청 처리 중 서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
    ):
        assert marker in client


def test_chat_v1_behavior_and_next_only_exposure_markers_are_preserved() -> None:
    thread = _read("frontend/src/features/chat/components/message-thread-client.tsx")
    listing = _read("frontend/src/features/chat/components/messages-client.tsx")
    for marker in (
        'message.error_code === "model_busy"',
        "message.id === latestMessageId",
        'maxLength={2000}',
        'event.key === "Enter" && !event.shiftKey',
        "답장 중",
        "다시 시도 중",
        'router.replace("/messages")',
    ):
        assert marker in thread
    for marker in (
        'router.replace("/login")',
        'aria-label="쪽지 내역 삭제"',
        ': `/messages/${encodeURIComponent(thread.id)}`;',
    ):
        assert marker in listing
    navigation = _read(
        "frontend/src/lib/navigation/device-navigation.ts"
    )
    assert '"/messages"' in navigation
    assert 'id: `next-only-${routeFamily.slice(1)}`' in navigation
    assert 'static: "unsupported"' in navigation
