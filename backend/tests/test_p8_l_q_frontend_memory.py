from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend/src"
DESKTOP = ROOT / "desktop"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_memory_feature_is_feature_first_and_shared_by_next_and_static() -> None:
    public = _read("frontend/src/features/memory/public.ts")
    next_page = _read("frontend/src/app/memory/page.tsx")
    next_compatibility = _read("frontend/src/app/memory-explorer/page.tsx")
    static_router = _read("frontend/src/composition/static-product-router.tsx")

    assert 'from "@/features/memory/public"' in next_page
    assert "<MemoryWorkspace" in next_page
    assert 'redirect("/memory")' in next_compatibility
    assert 'from "@/features/memory/public"' in static_router
    assert 'pathname === "/memory"' in static_router
    assert 'pathname === "/memory-explorer"' in static_router
    assert 'route="/memory"' in static_router
    assert "MemoryWorkspace" in public
    assert "MemoryScopeSummary" in public
    assert "WorldChatEvidenceInspector" in public
    assert "@/components" not in "\n".join(
        path.read_text(encoding="utf-8")
        for path in (FRONTEND / "features/memory").rglob("*.ts*")
    )


def test_memory_surface_preserves_q_reads_and_adds_r_owner_control() -> None:
    client = _read("frontend/src/features/memory/api/memory-client.ts")
    workspace = _read("frontend/src/features/memory/ui/memory-workspace.tsx")
    inspector = _read(
        "frontend/src/features/memory/ui/world-chat-evidence-inspector.tsx"
    )

    for getter in (
        "getMemorySetting",
        "listMemoryItems",
        "getMemoryItem",
        "getWorldChatEvidence",
    ):
        assert f"function {getter}" in client
    for mutation in (
        "updateMemorySetting",
        "setMemoryPin",
        "correctMemoryItem",
        "deleteMemoryItem",
    ):
        assert f"function {mutation}" in client
    assert 'mutate !== "available"' in client
    assert "mutationLockRef" in workspace
    assert "expected_version" in workspace
    assert "idempotencyKey" in workspace
    for copy in (
        "기억을 불러오는 중",
        "관리할 수 있는 기억 범위가 없어요",
        "기억을 불러오지 못했어요",
        "아직 저장된 기억이 없어요",
        "근거를 확인하는 중",
        "현재 표시할 수 있는 근거가 없습니다.",
        "확인 불가",
        "삭제됨",
    ):
        assert copy in workspace or copy in inspector


def test_chat_shows_only_deterministic_evidence_capability_and_safe_dialog() -> None:
    chat = _read("frontend/src/features/chat/ui/world-chat.tsx")
    contract = _read("frontend/src/features/chat/model/world-chat-contract.ts")
    inspector = _read(
        "frontend/src/features/memory/ui/world-chat-evidence-inspector.tsx"
    )

    assert "thread.evidence_summaries.find" in chat
    assert "근거 {evidence.count}개 보기" in chat
    assert "<WorldChatEvidenceInspector" in chat
    assert "evidence_summaries" in contract
    assert "item.excerpt ?" in inspector
    for forbidden in (
        "source_id",
        "source_revision",
        "canonical_locator",
        "provider_prompt",
        "raw_query",
    ):
        assert forbidden not in inspector


def test_memory_window_is_wide_singleton_and_phone_rejects_memory_route() -> None:
    product_windows = _read("desktop/src-tauri/src/product_windows.rs")
    product_window = _read("frontend/src/shared/desktop/product-window.ts")
    navigation = _read("frontend/src/features/device-shell/model/device-navigation.ts")

    assert '"memory"' in product_windows
    assert '"/memory"' in product_windows
    assert "memory_window_rejects_unscoped_or_unsafe_query_parameters" in product_windows
    assert 'validate_product_route(ProductWindowKind::Phone, "/memory").is_err()' in product_windows
    assert '| "memory"' in product_window
    assert 'id: "memory"' in navigation


def test_memory_workspace_has_narrow_reflow_and_no_raw_colors() -> None:
    css = _read("frontend/src/features/memory/ui/memory-workspace.module.css")

    assert "@media (max-width: 799px)" in css
    assert "grid-template-columns: 1fr" in css
    assert "var(--color-" in css
    assert "#" not in css
