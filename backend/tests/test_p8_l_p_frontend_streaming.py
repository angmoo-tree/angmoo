from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHAT_UI = ROOT / "frontend/src/features/chat/ui/world-chat.tsx"
CHAT_CSS = ROOT / "frontend/src/features/chat/ui/world-chat.module.css"
CHAT_CLIENT = ROOT / "frontend/src/features/chat/api/world-chat-client.ts"


def test_world_chat_exposes_one_delayed_typing_presence_and_crg_delta_only() -> None:
    ui = CHAT_UI.read_text(encoding="utf-8")
    client = CHAT_CLIENT.read_text(encoding="utf-8")

    assert "}, 300);" in ui
    assert "<span>입력 중</span>" in ui
    assert 'event.type === "delta"' in ui
    assert 'phase: "streaming"' in ui
    assert "current.text + text" in ui
    assert "activeGenerationRef.current !== scope" in ui
    assert "streamControllerRef.current?.abort()" in ui
    assert 'event.type === "failed"' in ui
    assert 'text: ""' in ui
    assert 'keys.join(",") !== "text"' in client
    assert "world_chat_stream_event_invalid" in client
    for forbidden in (
        "SQLite를 검색하는 중",
        "LadybugDB를 검색하는 중",
        "Evidence를 검증하는 중",
        "관계를 확인하는 중",
        "기억을 살펴보는 중",
    ):
        assert forbidden not in ui


def test_world_chat_keeps_send_and_response_retry_as_separate_states() -> None:
    ui = CHAT_UI.read_text(encoding="utf-8")
    css = CHAT_CSS.read_text(encoding="utf-8")

    assert "메시지를 보내지 못했어요." in ui
    assert "다시 보내기" in ui
    assert "답장을 만들지 못했어요." in ui
    assert "다시 시도" in ui
    assert "다시 시도 중" in ui
    assert "failed_request_id: failed.request_id" in ui
    assert "sendFailure.idempotencyKey" in ui
    assert "data-response-slot={generation.request.response_slot_id}" in ui
    assert "--color-state-danger-surface" in css
    assert "prefers-reduced-motion" in css
