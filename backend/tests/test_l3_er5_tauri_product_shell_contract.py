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
        "HEALTH_FAILURE_LIMIT",
        "consecutive_health_failures",
        "sidecar_terminated",
    ):
        assert marker in runtime or marker in host
    assert "PyInstaller 6.16.0" in build
    assert "System.Security.Cryptography.SHA256" in build
    assert 'listener.bind(("127.0.0.1", 0))' in sidecar
    assert '"sidecar.owner.json"' in sidecar
    assert '"sidecar.endpoint.json"' in sidecar
    assert "launch_token" not in sidecar.split("publish_endpoint", 1)[1].split(
        "def release", 1
    )[0]
    assert "hmac.compare_digest" in middleware
    for forbidden in ("execute_sql", "execute_cypher", "raw_shell"):
        assert forbidden not in runtime

    runtime_gate = _read("frontend/src/shared/runtime/desktop-runtime-gate.tsx")
    assert 'className="w-full min-w-0 max-w-sm text-center"' in runtime_gate
    assert 'className="mt-6 break-keep text-base' in runtime_gate


def test_phone_window_has_no_browser_chrome_and_applies_scaling_policy() -> None:
    config = json.loads(_read("desktop/src-tauri/tauri.conf.json"))
    phone = config["app"]["windows"][0]
    policy = _read("desktop/src-tauri/src/window_policy.rs")
    resize = _read("desktop/src-tauri/src/phone_resize.rs")

    assert phone["label"] == "main"
    assert phone["decorations"] is False
    assert phone["resizable"] is True
    assert phone["maximizable"] is False
    assert phone["transparent"] is True
    assert phone["backgroundColor"] == "#00000000"
    assert phone["shadow"] is False
    assert config["app"]["withGlobalTauri"] is True
    for marker in (
        "PHONE_TARGET_WIDTH",
        "PHONE_TARGET_HEIGHT",
        "phone_bounds_for_monitor",
        "scale_factor",
        "set_min_size",
        "set_max_size",
        "set_resizable(true)",
        "set_shadow(false)",
        "PHONE_MIN_SCALE",
        "PHONE_MAX_SCALE",
    ):
        assert marker in policy
    for marker in (
        "DwmSetWindowAttribute",
        "DWMWA_BORDER_COLOR",
        "DWMWA_COLOR_NONE",
        "DWMWA_WINDOW_CORNER_PREFERENCE",
        "DWMWCP_DONOTROUND_VALUE",
        "disable_compositor_rounding",
        "phone_contains_point",
        "HTNOWHERE",
        "SetWindowSubclass",
        "GetWindowSubclass",
        "RemoveWindowSubclass",
        "WM_SIZING",
        "WM_NCHITTEST",
        "WM_NCDESTROY",
        "WMSZ_LEFT",
        "WMSZ_RIGHT",
        "WMSZ_TOP",
        "WMSZ_BOTTOM",
        "WMSZ_TOPLEFT",
        "WMSZ_TOPRIGHT",
        "WMSZ_BOTTOMLEFT",
        "WMSZ_BOTTOMRIGHT",
        "HTTOPLEFT",
        "HTTOPRIGHT",
        "HTBOTTOMLEFT",
        "HTBOTTOMRIGHT",
    ):
        assert marker in resize
    assert "request_compositor_rounding" not in resize
    assert "DWMWCP_ROUND_VALUE" not in resize
    for aliased_region_marker in (
        "CreateRoundRectRgn",
        "SetWindowRgn",
        "DeleteObject",
    ):
        assert aliased_region_marker not in resize
    for scale in ("1.0", "1.25", "1.5"):
        assert scale in policy


def test_phone_static_shell_has_no_outer_margin_and_uses_manual_surface_drag() -> None:
    layout = _read("frontend/static-shell/app/layout.tsx")
    globals_css = _read("frontend/src/app/globals.css")
    frame = _read("frontend/src/shared/ui/device-frame.tsx")
    frame_css = _read("frontend/src/shared/ui/device-frame.module.css")
    bridge = _read("frontend/src/shared/desktop/desktop-window-bridge.tsx")
    static_router = _read("frontend/src/composition/static-product-router.tsx")

    assert 'data-angmoo-runtime-profile="tauri-static"' in layout
    assert 'body[data-angmoo-desktop-window="phone"]' in globals_css
    assert "background: transparent" in globals_css
    assert "data-tauri-drag-region" not in frame
    assert "width: 100vw" in frame_css
    assert "height: 100dvh" in frame_css
    assert 'dataset.angmooWindowDrag = "manual"' in bridge
    assert 'addEventListener("pointerdown", handlePointerDown, true)' in bridge
    assert "WINDOW_DRAG_INTERACTIVE_SELECTOR" in bridge
    assert 'invokeDesktopWindowCommand("start_product_window_drag")' in bridge
    assert "startDesktopWindowResize" in bridge
    assert "start_product_window_resize" in _read(
        "desktop/src-tauri/src/lib.rs"
    )
    assert "PHONE_RESIZE_EDGE_THICKNESS" in bridge
    assert "dataset.angmooWindowResize" in bridge
    assert 'data-window-drag-disabled="true"' in bridge
    assert "data-tauri-drag-region" not in bridge
    assert '<main className="min-h-screen bg-transparent" aria-live="polite">' in static_router
    assert '<p className="mt-3 text-xl font-bold text-[#251818]">제품 화면을 준비하고 있습니다...</p>' not in static_router


def test_wide_windows_use_explicit_route_boundaries_and_single_labels() -> None:
    windows = _read("desktop/src-tauri/src/product_windows.rs")
    bridge = _read("frontend/src/shared/desktop/desktop-window-bridge.tsx")
    desktop_runtime = _read("frontend/src/shared/desktop/product-window.ts")

    for marker in (
        'Self::Studio => "studio"',
        'Self::RelationshipGraph => "relationship-graph"',
        "studio_path_matches",
        "relationship_path_matches",
        "validate_product_route",
        "get_webview_window(kind.label())",
        "open_product_window_impl",
        ".min_inner_size(980.0, 680.0)",
        ".min_inner_size(900.0, 620.0)",
    ):
        assert marker in windows
    assert 'invoke("open_product_window"' in desktop_runtime
    assert "desktopWindowKindForRoute" in bridge
    assert "targetKind === currentKind" in bridge
    world_app = _read("frontend/src/features/world-app/ui/world-app.tsx")
    product_routes = _read("frontend/src/shared/navigation/product-routes.ts")
    assert "relationshipGraphRoute(ownerActor.character_id, worldId)" in world_app
    assert "내 조종 앵무 관계망 열기" in world_app
    assert "export function relationshipGraphRoute" in product_routes


def test_static_and_next_profiles_share_the_same_window_bridge() -> None:
    next_layout = _read("frontend/src/app/layout.tsx")
    static_layout = _read("frontend/static-shell/app/layout.tsx")
    router = _read("frontend/src/composition/static-product-router.tsx")
    config = json.loads(_read("desktop/src-tauri/tauri.conf.json"))

    assert "<DesktopWindowBridge />" in next_layout
    assert "<DesktopWindowBridge />" in static_layout
    assert "currentDesktopRoute" in router
    assert "subscribeDesktopRoute" in router
    assert config["build"]["devUrl"] == "http://127.0.0.1:3000"
    assert config["build"]["frontendDist"] == "../../frontend/out"


def test_memory_explorer_is_an_explicit_inactive_placeholder() -> None:
    contract = _read(
        "frontend/src/features/device-home/model/device-home-contract.ts"
    )
    assert 'id: "memory-explorer"' in contract
    assert 'label: "Memory Explorer"' in contract
    assert 'availability: "planned"' in contract


def test_desktop_build_outputs_never_enter_docker_build_context() -> None:
    dockerignore = _read(".dockerignore")
    for ignored_output in (
        "**/node_modules",
        "**/.next",
        "**/out",
        "**/target",
    ):
        assert ignored_output in dockerignore
