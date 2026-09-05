from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_ROOT = REPO_ROOT / "frontend" / "src"
DESKTOP_ROOT = REPO_ROOT / "desktop" / "src-tauri"


def _frontend(relative: str) -> str:
    return (FRONTEND_ROOT / relative).read_text(encoding="utf-8")


def _desktop(relative: str) -> str:
    return (DESKTOP_ROOT / relative).read_text(encoding="utf-8")


def test_world_package_import_is_available_from_home_studio_and_static_router() -> None:
    device = _frontend("features/device-home/utils/device-home-presentation.ts")
    studio = _frontend("features/creator-studio/model/creator-studio-contract.ts")
    dashboard = _frontend("features/creator-studio/ui/creator-studio-dashboard.tsx")
    static_router = _frontend("composition/static-product-router.tsx")
    import_page = _frontend("app/studio/import/page.tsx")

    home_entry = device.split('id: "world-import"', 1)[1].split("},", 1)[0]
    import_entry = studio.split('id: "import"', 1)[1].split("},", 1)[0]
    assert 'availability: "available"' in home_entry
    assert 'availability: "available"' in import_entry
    assert "Package 가져오기" in dashboard
    assert 'pathname === "/studio/import"' in static_router
    assert "StudioImportRouteClient" in static_router
    assert "StudioImportRouteClient" in import_page


def test_import_ui_uses_file_selection_digest_approval_and_atomic_navigation() -> None:
    source = _frontend(
        "features/world-packages/world-package-import-client.tsx"
    )
    assert 'type="file"' in source
    assert "WORLD_PACKAGE_EXTENSION" in source
    assert "prepared.preview.content_digest" in source
    assert "commitWorldPackageImport" in source
    assert "discardWorldPackageImport" in source
    assert "Device Home에서 보기" in source
    assert "studioWorldRoute(result.imported_world_id)" in source
    assert "서명 없음" in source
    assert "이전 가져오기 미리보기를 정리하지 못해 새 파일을 열지 않았습니다" in source
    assert "return;" in source.split("이전 가져오기 미리보기를 정리하지 못해 새 파일을 열지 않았습니다", 1)[1]


def test_export_ui_has_preview_browser_delivery_and_opaque_native_save_as() -> None:
    creator = _frontend("components/world-creator-client.tsx")
    panel = _frontend(
        "features/world-packages/world-package-export-panel.tsx"
    )
    native = _frontend("features/world-packages/native-delivery.ts")
    host = _desktop("src/world_package_delivery.rs")
    capability = _desktop("capabilities/product-shell.json")

    assert "WorldPackageExportPanel" in creator
    assert "previewWorldPackageExport" in panel
    assert "triggerBrowserWorldPackageDownload" in panel
    assert "selectNativeWorldPackageDestination" in panel
    assert "acknowledgeNativeWorldPackageDelivery" in panel
    assert "취소했습니다. 파일과 성공 이력은 생성되지 않았습니다" in panel
    assert "destinationToken" in native
    assert "destinationPath" not in native
    assert "atomic_write" in host
    assert "world_package_destination" in host
    assert "fs:" not in capability
    assert "dialog:" not in capability
    assert "pendingCleanup" in panel
    assert "retryCleanup" in panel
    assert "실패 작업 정리 후 다시 시도" in panel
