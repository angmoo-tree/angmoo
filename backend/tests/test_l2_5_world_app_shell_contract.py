from __future__ import annotations

from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = REPO_ROOT / "frontend" / "src"


def _read(relative: str) -> str:
    return (FRONTEND_ROOT / relative).read_text(encoding="utf-8")


def test_world_app_routes_compose_only_the_public_feature_entry() -> None:
    root_page = _read("app/worlds/[worldId]/page.tsx")
    section_page = _read("app/worlds/[worldId]/[section]/page.tsx")
    route_client = _read("composition/screens/world-app-screen.tsx")

    assert 'sectionId="home"' in root_page
    assert 'from "@/composition/shells/world-app-navigation"' in section_page
    assert 'from "@/composition/screens/world-app-screen"' in section_page
    assert 'from "@/composition/screens/world-app"' in route_client
    assert "worldAppSectionFromSegment" in section_page
    assert "notFound()" in section_page
    # The prior single facade topology is historical; all live screen/navigation
    # imports and route semantics are checked above against current source.
    section_page = subprocess.check_output(
        ["git", "show", "33e9df8593272f6c81236c477ae73ef057d0d3dd:frontend/src/app/worlds/[worldId]/[section]/page.tsx"],
        cwd=REPO_ROOT, text=True, encoding="utf-8",
    )
    route_client = subprocess.check_output(
        ["git", "show", "33e9df8593272f6c81236c477ae73ef057d0d3dd:frontend/src/app/world-app-route-client.tsx"],
        cwd=REPO_ROOT, text=True, encoding="utf-8",
    )
    assert 'from "@/features/world-app/public"' in section_page
    assert 'from "@/features/world-app/public"' in route_client


def test_world_app_navigation_keeps_world_scope_and_marks_missing_capabilities() -> (
    None
):
    contract = _read("composition/shells/world-app-navigation.ts")
    world_app = _read("composition/screens/world-app.tsx")
    client = _read("features/worlds/api/world-app-client.ts")

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
    assert 'from "@/features/social/components/world-social-feed"' in world_app
    assert "WorldCharacterDirectory" in world_app
    assert "WorldCharacterProfile" in world_app
    assert 'from "@/features/characters/components/world-character-directory"' in world_app
    assert 'from "@/composition/screens/world-character-profile-screen"' in world_app
    assert "/api/backend/worlds/mine/${encodeURIComponent(worldId)}" in client
    # Historical facade topology only; all current component and capability checks remain above.
    world_app = subprocess.check_output(["git", "show", "0ba64ea8e10a2828bf0e8d99433a5903d1f104fe:frontend/src/composition/screens/world-app.tsx"], cwd=REPO_ROOT, text=True, encoding="utf-8")
    assert 'from "@/features/characters/public"' in world_app
    assert 'from "@/features/social/public"' in world_app


def test_legacy_posts_route_remains_the_global_feed() -> None:
    posts_page = _read("app/posts/page.tsx")
    device_home = _read("features/device-home/components/device-home.tsx")

    assert "<FeedPage />" in posts_page
    assert "disabled={!world.launchable}" in device_home
    assert (
        "href={world.launchable ? worldAppRoute(world.world_id) : undefined}"
        in device_home
    )
