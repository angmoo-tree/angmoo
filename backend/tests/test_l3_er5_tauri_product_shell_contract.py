from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_tauri_product_shell_is_pinned_and_has_no_sidecar_or_raw_shell_scope() -> None:
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
    assert "sidecar" not in cargo.lower()
    assert "tauri-plugin-shell" not in cargo


def test_phone_window_has_no_browser_chrome_and_applies_scaling_policy() -> None:
    config = json.loads(_read("desktop/src-tauri/tauri.conf.json"))
    phone = config["app"]["windows"][0]
    policy = _read("desktop/src-tauri/src/window_policy.rs")

    assert phone["label"] == "main"
    assert phone["decorations"] is False
    assert phone["resizable"] is False
    assert phone["maximizable"] is False
    assert config["app"]["withGlobalTauri"] is True
    for marker in (
        "PHONE_TARGET_WIDTH",
        "PHONE_TARGET_HEIGHT",
        "phone_size_for_monitor",
        "scale_factor",
        "set_min_size",
        "set_max_size",
        "set_resizable(false)",
    ):
        assert marker in policy
    for scale in ("1.0", "1.25", "1.5"):
        assert scale in policy


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
