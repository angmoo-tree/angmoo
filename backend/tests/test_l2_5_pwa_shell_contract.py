from __future__ import annotations

import struct
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = REPOSITORY_ROOT / "frontend"


def _read(relative_path: str) -> str:
    return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")


def _png_size(path: Path) -> tuple[int, int]:
    payload = path.read_bytes()
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    return struct.unpack(">II", payload[16:24])


def test_manifest_defines_optional_standalone_device_home() -> None:
    manifest = _read("frontend/src/app/manifest.ts")

    for marker in (
        'name: "Angmoo"',
        'short_name: "Angmoo"',
        'start_url: "/"',
        'scope: "/"',
        'display: "standalone"',
        'src: "/pwa-icon-192.png"',
        'src: "/pwa-icon-512.png"',
        'src: "/pwa-maskable-512.png"',
    ):
        assert marker in manifest


def test_pwa_icons_are_real_png_assets_with_declared_sizes() -> None:
    assert _png_size(FRONTEND_ROOT / "public" / "pwa-icon-192.png") == (192, 192)
    assert _png_size(FRONTEND_ROOT / "public" / "pwa-icon-512.png") == (512, 512)
    assert _png_size(FRONTEND_ROOT / "public" / "pwa-maskable-512.png") == (
        512,
        512,
    )


def test_service_worker_is_lifecycle_only_and_caches_no_application_data() -> None:
    worker = _read("frontend/public/sw.js")

    assert "ANGMOO_WORKER_VERSION" in worker
    assert 'addEventListener("install"' in worker
    assert 'addEventListener("activate"' in worker
    assert 'addEventListener("fetch"' not in worker
    assert "caches." not in worker
    assert "CacheStorage" not in worker
    assert "/api/" not in worker
    assert "offline" not in worker.lower()


def test_root_layout_registers_optional_worker_without_blocking_render() -> None:
    layout = _read("frontend/src/app/layout.tsx")
    lifecycle = _read(
        "frontend/src/features/pwa-shell/ui/pwa-service-worker-lifecycle.tsx"
    )

    assert "<PwaServiceWorkerLifecycle />" in layout
    assert 'navigator.serviceWorker.register(' in lifecycle
    assert 'updateViaCache: "none"' in lifecycle
    assert "registration.update()" in lifecycle
    assert "registration.unregister()" in lifecycle
    assert "return null" in lifecycle


def test_service_worker_delivery_forces_update_revalidation() -> None:
    config = _read("frontend/next.config.ts")

    assert 'source: "/sw.js"' in config
    assert 'value: "no-cache, no-store, must-revalidate"' in config
    assert 'key: "Service-Worker-Allowed"' in config
