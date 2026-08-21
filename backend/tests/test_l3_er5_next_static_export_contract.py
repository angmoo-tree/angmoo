from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_static_profile_reuses_product_source_and_has_no_server_hooks() -> None:
    config = _read("frontend/static-shell/next.config.ts")
    router = _read(
        "frontend/src/composition/static-product-router.tsx"
    )

    assert 'output: "export"' in config
    assert "headers()" not in config
    assert "redirects()" not in config
    assert "rewrites()" not in config
    for marker in (
        "DeviceHomeRouteClient",
        "StudioRouteClient",
        "WorldAppRouteClient",
        "WorldCreatorClient",
        "WorldCharacterAutonomySetupClient",
        "RelationshipGraphClient",
        "AgentDetailClient",
        "PostListClient",
        "PostDetailClient",
        "SettingsClient",
    ):
        assert marker in router


def test_runtime_adapter_restricts_injection_to_loopback_and_maps_proxy_paths() -> None:
    runtime = _read("frontend/src/shared/runtime/runtime-config.ts")
    assert 'new Set(["127.0.0.1", "localhost", "[::1]"])' in runtime
    assert 'parsed.protocol !== "http:"' in runtime
    assert 'input.startsWith("/api/backend")' in runtime
    assert '`${runtime.apiBaseUrl}/api/v1' in runtime
    assert 'input.startsWith("/media/")' in runtime
    assert "runtime.launchToken && isSidecarRequest" in runtime
    assert 'headers.set("X-Angmoo-Launcher-Token"' in runtime


def test_static_route_matrix_and_dynamic_fallback_are_explicit() -> None:
    router = _read(
        "frontend/src/composition/static-product-router.tsx"
    )
    build = _read("frontend/scripts/build-static.mjs")
    for route_marker in (
        'pathname === "/"',
        'pathname === "/studio"',
        'pathname === "/studio/worlds/new"',
        'pathname === "/posts"',
        'pathname === "/settings"',
        'pathname === "/login"',
        'segments[0] === "studio"',
        'segments[0] === "worlds"',
        'segments[0] === "agents"',
        'segments[0] === "posts"',
        'segments[0] === "characters"',
        'segments[4] === "autonomy-setup"',
        'segments[4] === "relationship-graph"',
    ):
        assert route_marker in router
    assert 'join(productOutput, "index.html")' in build
    assert 'join(productOutput, "404.html")' in build


def test_static_profile_disables_pwa_and_leaves_outputs_untracked() -> None:
    lifecycle = _read(
        "frontend/src/features/pwa-shell/ui/pwa-service-worker-lifecycle.tsx"
    )
    build = _read("frontend/scripts/build-static.mjs")
    ignore = _read(".gitignore")
    assert "isStaticFrontendProfile()" in lifecycle
    assert "unregisterAngmooServiceWorker()" in lifecycle
    assert '"sw.js"' not in build
    assert "out/" in ignore
    assert "frontend/static-shell/out/" in ignore


def test_package_exposes_static_build_without_changing_default_build() -> None:
    package = json.loads(_read("frontend/package.json"))
    assert package["scripts"]["build"] == "next build"
    assert package["scripts"]["build:static"] == "node ./scripts/build-static.mjs"


def test_static_output_exists_when_explicitly_requested() -> None:
    if not (FRONTEND / "out" / "index.html").exists():
        return
    assert (FRONTEND / "out" / "404.html").read_bytes() == (
        FRONTEND / "out" / "index.html"
    ).read_bytes()
    assert not (FRONTEND / "out" / "sw.js").exists()
