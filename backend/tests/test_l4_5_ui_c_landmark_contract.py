from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_phone_shell_is_the_only_main_landmark_owner_for_nested_routes() -> None:
    device_shell = _read(
        "frontend/src/features/device-shell/ui/device-shell.tsx"
    )
    app_shell = _read("frontend/src/components/app-shell.tsx")

    assert "<main" in device_shell
    assert 'data-main-landmark-owner="device-shell"' in device_shell
    assert "<main" not in app_shell

    for relative_path, content_marker in (
        (
            "frontend/src/components/world-character-autonomy-setup-client.tsx",
            'data-product-content="autonomy-setup"',
        ),
        (
            "frontend/src/app/angmoo-api/page.tsx",
            'data-product-content="angmoo-api"',
        ),
        (
            "frontend/src/app/licenses/page.tsx",
            'data-product-content="licenses"',
        ),
    ):
        source = _read(relative_path)
        assert "<main" not in source
        assert content_marker in source


def test_wide_product_shells_own_their_main_landmark() -> None:
    relationship_frame = _read(
        "frontend/src/features/relationships/ui/relationship-graph-frame.tsx"
    )
    relationship_client = _read(
        "frontend/src/features/relationships/ui/relationship-graph-client.tsx"
    )
    creator_shell = _read(
        "frontend/src/features/creator-studio/ui/creator-studio-shell.tsx"
    )
    creator_client = _read("frontend/src/components/world-creator-client.tsx")

    assert "<main" in relationship_frame
    assert (
        'data-main-landmark-owner="relationship-graph"'
        in relationship_frame
    )
    assert "<main" not in relationship_client
    assert 'data-product-content="relationship-graph"' in relationship_client

    assert "<main" in creator_shell
    assert 'data-main-landmark-owner="creator-studio"' in creator_shell
    assert "<main" not in creator_client
    assert 'data-product-content="creator-studio-world"' in creator_client
