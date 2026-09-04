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


def test_world_app_navigation_keeps_world_scope_and_marks_missing_capabilities() -> (
    None
):
    contract = _read("features/world-app/model/world-app-contract.ts")
    world_app = _read("features/world-app/ui/world-app.tsx")
    client = _read("features/world-app/api/world-app-client.ts")

    assert "encodeURIComponent(worldId)" in _read("lib/navigation/product-routes.ts")
    for segment in ("feed", "chat", "characters", "relationships"):
        assert f'segment: "{segment}"' in contract
    # P8-L-D makes Chat available as a World-scoped, read-only list/detail
    # surface. P8-L-E activates the same-World Character directory/profile
    # surface, so no World App section remains reserved at this boundary.
    assert contract.count('availability: "unavailable"') == 0
    assert 'id: "feed"' in contract
    assert 'id: "relationships"' in contract
    assert 'availability: "available"' in contract
    assert "worldAppSectionRoute(worldId, section)" in world_app
    assert "relationshipGraphRoute(ownerActor.character_id, worldId)" in world_app
    assert "다른 World로 자동 이동하지 않습니다" in world_app
    assert "WorldSocialFeed" in world_app
    assert 'from "@/features/social/public"' in world_app
    assert "WorldCharacterDirectory" in world_app
    assert "WorldCharacterProfile" in world_app
    assert 'from "@/features/characters/public"' in world_app
    assert "/api/backend/worlds/mine/${encodeURIComponent(worldId)}" in client


def test_legacy_posts_route_remains_the_global_feed() -> None:
    posts_page = _read("app/posts/page.tsx")
    device_home = _read("features/device-home/components/device-home.tsx")

    assert "<FeedPage />" in posts_page
    assert "disabled={!world.launchable}" in device_home
    assert (
        "href={world.launchable ? worldAppRoute(world.world_id) : undefined}"
        in device_home
    )
