from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_tauri_product_shell_is_pinned_and_keeps_sidecar_out_of_js_shell_scope() -> None:
    cargo = _read("desktop/src-tauri/Cargo.toml")
    package = json.loads(_read("desktop/package.json"))
    capability = json.loads(
        _read("desktop/src-tauri/capabilities/product-shell.json")
    )

    assert 'tauri = { version = "=2.11.5"' in cargo
    assert 'tauri-build = { version = "=2.6.3"' in cargo
    assert package["devDependencies"]["@tauri-apps/cli"] == "2.11.4"
    assert capability["permissions"] == ["core:default"]
    serialized = json.dumps(capability, sort_keys=True)
    assert "shell:" not in serialized
    assert 'tauri-plugin-shell = "=2.3.5"' in cargo
    assert 'tauri-plugin-single-instance = "=2.4.3"' in cargo
    assert 'features = ["macos-private-api"]' in cargo
    config = json.loads(_read("desktop/src-tauri/tauri.conf.json"))
    assert config["bundle"]["externalBin"] == ["binaries/angmoo-sidecar"]
    assert config["app"]["macOSPrivateApi"] is True


def test_product_sidecar_has_fixed_commands_hash_and_lifecycle_contract() -> None:
    runtime = _read("desktop/src-tauri/src/desktop_runtime.rs")
    host = _read("desktop/src-tauri/src/lib.rs")
    build = _read("desktop/scripts/build-sidecar.ps1")
    sidecar = _read("backend/app/runtime/desktop_sidecar.py")
    middleware = _read("backend/app/core/desktop_loopback.py")

    for marker in (
        "verify_packaged_sidecar",
        "ANGMOO_SIDECAR_SHA256",
        'Uuid::new_v4()',
        'sidecar("angmoo-sidecar")',
        "desktop_runtime_status",
        "retry_desktop_runtime",
        '"/__angmoo/desktop/shutdown"',
        "desktop_sidecar_health_lost",
        "const HEALTH_FAILURE_LIMIT: u8 = 15;",
        "consecutive_health_failures",
        "drain_sidecar_events",
    ):
        assert marker in runtime or marker in host
    assert "PyInstaller 6.16.0" in build
    assert "System.Security.Cryptography.SHA256" in build
    normalized_build = build.replace("\\", "/")
    assert "sqlite_versions/manifests" in normalized_build
    assert "ladybug_versions/manifests" in normalized_build
    assert "--add-data $sqliteManifestData" in build
    assert "--add-data $ladybugManifestData" in build
    assert 'listener.bind(("127.0.0.1", 0))' in sidecar
    assert '"sidecar.owner.json"' in sidecar
    assert '"sidecar.endpoint.json"' in sidecar
    assert "launch_token" not in sidecar.split("publish_endpoint", 1)[1].split(
        "def release", 1
    )[0]
    assert "hmac.compare_digest" in middleware
    for forbidden in ("execute_sql", "execute_cypher", "raw_shell"):
        assert forbidden not in runtime

    runtime_gate = _read("frontend/src/composition/providers/desktop-runtime-gate.tsx")
    assert 'width: "min(24rem, calc(100vw - 4rem))"' in runtime_gate
    assert 'wordBreak: "keep-all"' in runtime_gate
    assert "sidecar_terminated" not in runtime


def test_phone_window_has_no_browser_chrome_and_applies_scaling_policy() -> None:
    """Approved C07/C08: normal OS caption and independent client geometry."""
    config = json.loads(_read("desktop/src-tauri/tauri.conf.json"))
    windows = _read("desktop/src-tauri/src/product_windows.rs")
    policy = _read("desktop/src-tauri/src/window_policy.rs")
    host = _read("desktop/src-tauri/src/lib.rs")
    assert config["app"]["windows"] == []
    assert config["app"]["withGlobalTauri"] is True
    for marker in ("ProductWindowKind::Phone.label()", "crate::window_policy::MAIN_INITIAL_WIDTH", "crate::window_policy::MAIN_INITIAL_HEIGHT",
                   ".decorations(true)", ".transparent(false)", ".resizable(true)", ".maximizable(true)"):
        assert marker in windows
    for marker in ("product_geometry_for_work_area", "monitor.work_area()", "outer_size()",
                   "inner_size()", "set_min_size", "set_max_size(None", "set_position", "scale_factor"):
        assert marker in policy
    assert "mod phone_resize" not in host
    assert "PHONE_ASPECT_RATIO" not in policy
    assert not (ROOT / "desktop/src-tauri/src/phone_resize.rs").exists()
    assert "start_product_window_resize" not in host


def test_phone_static_shell_has_no_outer_margin_and_uses_manual_surface_drag() -> None:
    """Approved C03/C05/C09/C11: shared remaining-height viewport, OS drag."""
    layout = _read("frontend/static-shell/app/layout.tsx")
    frame = _read("frontend/src/components/ui/device-frame.tsx")
    frame_css = _read("frontend/src/components/ui/device-frame.module.css")
    bridge = _read("frontend/src/composition/providers/desktop-window-bridge.tsx")
    viewport = _read("frontend/src/composition/shells/product-viewport.tsx")
    toolbar = _read("frontend/src/composition/navigation/desktop-navigation-toolbar.tsx")
    assert 'data-angmoo-runtime-profile="tauri-static"' in layout
    assert "ProductViewport" in layout
    assert "DesktopNavigationToolbar" in viewport
    assert 'data-device-scroll-owner="true"' in frame
    assert 'data-device-titlebar-inset="true"' not in frame
    assert "max-width: var(--product-body-max-width)" in frame_css
    assert "height: 100%" in frame_css
    assert "border-radius" not in frame_css
    assert "border:" not in frame_css
    assert "pointerdown" not in bridge
    assert "start_product_window_drag" not in bridge
    assert "installDesktopHistory" in bridge
    assert 'data-desktop-navigation="true"' in toolbar
    assert "event.nativeEvent.isComposing" in toolbar
    windows = _read("desktop/src-tauri/src/product_windows.rs")
    assert "on_navigation" in windows
    assert "on_new_window" in windows
    assert "NewWindowResponse::Deny" in windows
    assert "validate_external_product_link" in windows
    capabilities = json.loads(_read("desktop/src-tauri/capabilities/product-shell.json"))
    assert capabilities["permissions"] == ["core:default"]


def test_wide_windows_use_explicit_route_boundaries_and_single_labels() -> None:
    windows = _read("desktop/src-tauri/src/product_windows.rs")
    bridge = _read("frontend/src/composition/providers/desktop-window-bridge.tsx")
    desktop_runtime = _read("frontend/src/lib/desktop/product-window.ts")

    for marker in (
        'Self::Studio => "studio"',
        'Self::RelationshipGraph => "relationship-graph"',
        "studio_path_matches",
        "relationship_path_matches",
        "validate_product_route",
        "get_webview_window(kind.label())",
        "open_product_window_impl",
        ".min_inner_size(480.0, 480.0)",
    ):
        assert marker in windows
    assert 'invoke("open_product_window"' in desktop_runtime
    assert "navigateDesktopProductRoute" in bridge
    assert "targetKind === state.kind" in desktop_runtime
    world_app = _read("frontend/src/composition/screens/world-app.tsx")
    product_routes = _read("frontend/src/lib/navigation/product-routes.ts")
    assert "relationshipGraphRoute(ownerActor.character_id, worldId)" in world_app
    assert "내 조종 앵무 관계망 열기" in world_app
    assert "export function relationshipGraphRoute" in product_routes


def test_phone_product_window_allowlist_matches_local_route_capabilities() -> None:
    windows = _read("desktop/src-tauri/src/product_windows.rs")

    # These routes are rendered by the shared static product router and must be
    # accepted by the native Phone boundary as direct-open and navigation targets.
    assert '["settings"] | ["login"] | ["posts"] | ["agents"]' in windows
    assert '["worlds", world_id, "posts", post_id]' in windows

    # `/worlds/new` is a Browser compatibility alias for Creator Studio, not a
    # valid dynamic Phone World.  The native boundary must therefore fail closed.
    assert "fn safe_world_id" in windows
    assert 'decoded != "new" && safe_decoded_segment(&decoded)' in windows
    assert "fn decode_route_segment" in windows


def test_static_phone_hides_unsupported_links_and_uses_its_scroll_owner() -> None:
    capability = _read(
        "frontend/src/lib/navigation/device-navigation.ts"
    )
    product_link = _read(
        "frontend/src/components/navigation/local-product-link.tsx"
    )
    feed = _read("frontend/src/composition/screens/post-list-screen.tsx")
    social_post_row = _read(
        "frontend/src/features/social/components/social-post-row.tsx"
    )
    agent = _read("frontend/src/composition/screens/agent-detail-screen.tsx") + _read("frontend/src/features/characters/components/agent-detail-parts.tsx")
    pull_to_refresh = _read(
        "frontend/src/hooks/use-mobile-pull-to-refresh.ts"
    )
    scroll_viewport = _read(
        "frontend/src/lib/dom/scroll-viewport.ts"
    )
    static_router = _read("frontend/src/composition/static-product-router.tsx")

    assert "isStaticLocalProductRouteSupported" in capability
    assert 'data-product-route-unavailable="true"' in product_link
    assert 'aria-disabled="true"' in product_link
    assert 'role="link"' in product_link
    assert "event.stopPropagation()" in product_link
    assert "local-product-link.module.css" in product_link
    assert "SocialPostRow" in feed
    assert "LocalProductLink" in social_post_row
    assert "const canStartMessage = !isLocalAgent && !isStaticFrontendProfile()" in agent
    assert "getRuntimeConfig()?.apiBaseUrl ?? window.location.origin" in agent
    assert "resolveScrollEventTarget" in feed
    assert "resolveScrollEventTarget" in agent
    assert "resolveScrollEventTarget" in pull_to_refresh
    assert "export function isScrollNearBottom" in scroll_viewport
    assert "const [ready, setReady] = useState(false)" in static_router


def test_programmatic_navigation_respects_product_window_boundaries() -> None:
    desktop_runtime = _read("frontend/src/lib/desktop/product-window.ts")
    runtime_navigation = _read(
        "frontend/src/hooks/use-runtime-navigation.ts"
    )

    assert "export async function navigateDesktopProductRoute" in desktop_runtime
    assert "const targetKind = desktopWindowKindForRoute(normalized)" in desktop_runtime
    assert "if (targetKind === state.kind)" in desktop_runtime
    assert "await openDesktopProductWindow(targetKind, normalized)" in desktop_runtime
    assert (
        "desktopWindowKindForRoute(normalized) !== state.kind"
        in desktop_runtime
    )
    assert "if (isTauriDesktopRuntime())" in runtime_navigation
    assert "navigateDesktopProductRoute(href, replace)" in runtime_navigation
    tauri_branch = runtime_navigation.split(
        "if (isTauriDesktopRuntime())", maxsplit=1
    )[1].split("if (replace)", maxsplit=1)[0]
    assert "window.location" not in tauri_branch


def test_static_and_next_profiles_share_the_same_window_bridge() -> None:
    next_layout = _read("frontend/src/app/layout.tsx")
    static_layout = _read("frontend/static-shell/app/layout.tsx")
    router = _read("frontend/src/composition/static-product-router.tsx")
    config = json.loads(_read("desktop/src-tauri/tauri.conf.json"))

    assert "<DesktopWindowBridge />" in next_layout
    assert "<DesktopWindowBridge />" in static_layout
    assert "currentDesktopRoute" in router
    assert "subscribeDesktopRoute" in router
    assert 'return `${route.pathname}\\n${route.search}`;' in router
    assert 'const route = `${location.pathname}${location.search}`;' in router
    assert config["build"]["devUrl"] == "http://127.0.0.1:3000"
    assert config["build"]["frontendDist"] == "../../frontend/out"


def test_memory_read_surface_replaces_the_inactive_explorer_placeholder() -> None:
    contract = _read(
        "frontend/src/features/device-home/utils/device-home-presentation.ts"
    )
    assert 'id: "memory"' in contract
    assert 'label: "Memory"' in contract
    assert 'href: "/memory"' in contract
    assert 'availability: "available"' in contract
    assert 'id: "memory-explorer"' not in contract


def test_desktop_build_outputs_never_enter_docker_build_context() -> None:
    dockerignore = _read(".dockerignore")
    for ignored_output in (
        "**/node_modules",
        "**/.next",
        "**/out",
        "**/target",
    ):
        assert ignored_output in dockerignore
