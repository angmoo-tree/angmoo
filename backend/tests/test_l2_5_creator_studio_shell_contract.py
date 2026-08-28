from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = REPO_ROOT / "frontend" / "src"


def _read(relative: str) -> str:
    return (FRONTEND_ROOT / relative).read_text(encoding="utf-8")


def test_creator_studio_canonical_routes_use_public_feature_shell() -> None:
    dashboard_page = _read("app/studio/page.tsx")
    new_page = _read("app/studio/worlds/new/page.tsx")
    edit_page = _read("app/studio/worlds/[worldId]/page.tsx")
    import_page = _read("app/studio/import/page.tsx")

    for source in (dashboard_page, new_page, edit_page, import_page):
        assert 'from "@/features/creator-studio/public"' in source
    assert 'activeSection="worlds"' in dashboard_page
    assert 'activeSection="new-world"' in new_page
    assert "WorldCreatorClient" in new_page
    assert "WorldCreatorClient" in edit_page
    assert "StudioImportRouteClient" in import_page


def test_creator_studio_reads_owner_surface_and_groups_blocked_worlds() -> None:
    dashboard = _read(
        "features/creator-studio/ui/creator-studio-dashboard.tsx"
    )
    device_contract = _read("features/device-home/model/device-home-contract.ts")

    assert 'getLocalWorldSurface("creator_studio"' in dashboard
    assert '"live" | "draft" | "private" | "archived"' in dashboard
    assert "studioWorldRoute(world.world_id)" in dashboard
    assert "worldAppRoute(world.world_id)" in dashboard
    assert 'label: "Creator Studio"' in device_contract
    studio_entry = device_contract.split('id: "studio"', 1)[1].split("},", 1)[0]
    assert 'availability: "available"' in studio_entry


def test_legacy_creator_routes_redirect_to_canonical_studio_routes() -> None:
    legacy_new = _read("app/worlds/new/page.tsx")
    legacy_edit = _read("app/worlds/[worldId]/creator/page.tsx")
    creator = _read("components/world-creator-client.tsx")

    assert "redirect(PRODUCT_ROUTES.studioNewWorld)" in legacy_new
    assert "redirect(studioWorldRoute(worldId))" in legacy_edit
    assert "router.replace(studioWorldRoute(saved.world.id))" in creator
    assert '"/worlds/new"' not in creator
    assert "`/worlds/${worldId}/creator`" not in creator


def test_studio_shell_is_wide_and_preserves_small_viewport_accessibility() -> None:
    shell_css = _read("features/creator-studio/ui/creator-studio-shell.module.css")
    dashboard_css = _read(
        "features/creator-studio/ui/creator-studio-dashboard.module.css"
    )
    frame = _read("features/creator-studio/ui/creator-studio-frame.tsx")

    assert "grid-template-columns: minmax(210px, 260px) minmax(0, 1fr)" in shell_css
    assert "@media (max-width: 799px)" in shell_css
    assert "grid-template-columns: 1fr" in shell_css
    assert "width: min(100%, 1180px)" in dashboard_css
    assert 'href={PRODUCT_ROUTES.deviceHome}' in frame


def test_studio_world_character_surface_owns_fixture_lifecycle_orchestration() -> None:
    creator = _read("components/world-creator-client.tsx")
    surface = _read(
        "features/creator-studio/ui/studio-world-character-list.tsx"
    )
    create_client = _read("components/agent-create-client.tsx")
    browser_create_page = _read("app/agents/new/page.tsx")
    client = _read(
        "features/creator-studio/api/studio-world-character-client.ts"
    )

    assert "StudioWorldCharacterList" in creator
    assert "이 World의 캐릭터" in surface
    assert "활동 준비·상태 보기" in surface
    assert "/autonomy-setup`" in surface
    assert 'import Link from "next/link"' in surface
    assert "useRuntimeRouter" in surface
    assert "새 캐릭터 만들기" in surface
    assert (
        'const createHref = `/agents/new?worldId=${encodeURIComponent(worldId)}'
        '&returnTo=${encodeURIComponent(returnTo)}`;' in surface
    )
    assert "기존 캐릭터 연결" in surface
    assert "이 World에서 제거" in surface
    assert "생성·삭제는 P10-L에서 제공합니다." not in surface
    assert "?surface=studio" in client
    assert "/character-candidates" in client
    assert "/leave`" in client
    assert 'method: "POST"' not in surface
    assert 'method: "DELETE"' not in surface
    assert "useRuntimeSearchParams as useSearchParams" in create_client
    assert 'searchParams.get("worldId")' in create_client
    assert 'searchParams.get("returnTo")' in create_client
    assert "requestedReturnTo === expectedWorldReturnTo" in create_client
    assert "navigateDesktopProductRoute" in create_client
    assert "async function openWorldFixtureReturn" in create_client
    assert "created.character.id," in create_client
    assert "await navigateDesktopProductRoute(returnRoute)" in create_client
    assert "if (!result.handled)" in create_client
    assert "if (createdAgent)" in create_client
    assert "await openWorldFixtureReturn(createdAgent)" in create_client
    assert 'data-world-fixture-completion="created"' in create_client
    assert 'data-world-fixture-return-status={worldFixtureReturnStatus}' in create_client
    assert "Creator Studio로 다시 돌아가기" in create_client
    assert "생성된 앵무 보기" in create_client
    assert "<AgentCreateClient />" in browser_create_page


def test_local_character_creation_ui_has_no_hosted_saved_count_gate() -> None:
    create_client = _read("components/agent-create-client.tsx")
    dashboard = _read("components/agents-dashboard-client.tsx")
    agents_lib = _read("lib/agents.ts")
    combined = "\n".join((create_client, dashboard, agents_lib))

    for forbidden in (
        "MAX_LLM_AGENTS_PER_USER",
        "MAX_LOCAL_AGENTS_PER_USER",
        "MAX_AGENTS_PER_USER",
        "AgentQuotaCounts",
        "getAgentQuotaCounts",
        "AGENT_LIMIT_MESSAGE",
        "LLM_AGENT_LIMIT_MESSAGE",
        "LOCAL_AGENT_LIMIT_MESSAGE",
        "앵무 생성 제한",
        "한도 도달",
        "3/3",
    ):
        assert forbidden not in combined

    assert "setInitialAgentCount(agents.length)" in create_client
    assert "if (initialAgentCount === 0)" in create_client
    assert "<CreationModeSelector" in create_client
    assert "counts=" not in create_client
    assert "getAgentTypeCounts(agents)" in dashboard
    assert "서버 LLM ${agentTypeCounts.llm}개" in dashboard
    assert 'href="/agents/new"' in dashboard
