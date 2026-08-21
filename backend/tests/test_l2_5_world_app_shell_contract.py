from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = REPO_ROOT / "frontend" / "src"


def _read(relative: str) -> str:
    return (FRONTEND_ROOT / relative).read_text(encoding="utf-8")


def test_world_app_routes_compose_only_the_public_feature_entry() -> None:
    root_page = _read("app/worlds/[worldId]/page.tsx")
    section_page = _read("app/worlds/[worldId]/[section]/page.tsx")
    route_client = _read("app/world-app-route-client.tsx")

    assert 'sectionId="home"' in root_page
    assert 'from "@/features/world-app/public"' in section_page
    assert 'from "@/features/world-app/public"' in route_client
    assert "worldAppSectionFromSegment" in section_page
    assert "notFound()" in section_page


def test_world_app_navigation_keeps_world_scope_and_marks_missing_capabilities() -> None:
    contract = _read("features/world-app/model/world-app-contract.ts")
    world_app = _read("features/world-app/ui/world-app.tsx")
    client = _read("features/world-app/api/world-app-client.ts")

    assert "encodeURIComponent(worldId)" in _read(
        "shared/navigation/product-routes.ts"
    )
    for segment in ("feed", "chat", "characters", "relationships"):
        assert f'segment: "{segment}"' in contract
    assert contract.count('availability: "unavailable"') == 2
    assert 'id: "feed"' in contract
    assert 'id: "relationships"' in contract
    assert 'availability: "available"' in contract
    assert "worldAppSectionRoute(worldId, section)" in world_app
    assert "relationshipGraphRoute(ownerActor.character_id, worldId)" in world_app
    assert "다른 World로 자동 이동하지 않습니다" in world_app
    assert "WorldManualFeed" in world_app
    assert "/api/backend/worlds/mine/${encodeURIComponent(worldId)}" in client


def test_legacy_posts_route_remains_the_global_feed() -> None:
    posts_page = _read("app/posts/page.tsx")
    device_home = _read("features/device-home/ui/device-home.tsx")

    assert "<FeedPage />" in posts_page
    assert "const routeReady = world.launchable" in device_home
