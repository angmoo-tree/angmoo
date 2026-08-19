from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "backend" / "app"
EXECUTION_MAP = REPO_ROOT / "docs" / "architecture" / "l3-p1-p4-execution-map.md"
PUBLIC_BOUNDARIES = (
    "worlds",
    "world_characters",
    "routines",
    "routine_posts",
)


def _function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_l3_execution_map_records_exact_baseline_and_status() -> None:
    text = EXECUTION_MAP.read_text(encoding="utf-8")

    assert "b809bc2d748f8bcac82860447bcff3c816f93452" in text
    assert "IN PROGRESS / PR H CLOSEOUT" in text
    for boundary in PUBLIC_BOUNDARIES:
        assert f"app.domains.{boundary}.public" in text


def test_l3_current_entrypoints_track_completed_and_pending_migrations() -> None:
    expected = {
        APP_ROOT / "domains" / "worlds" / "infrastructure" / "sqlalchemy_world_creator.py": {
            "create_world",
            "update_world",
            "validate_world_definition",
            "publish_world",
        },
        APP_ROOT
        / "domains"
        / "world_characters"
        / "infrastructure"
        / "sqlalchemy_autonomous_setup.py": {
            "enter_world",
            "preflight_setup",
            "generate_setup",
            "retry_setup",
            "approve_setup",
        },
        APP_ROOT
        / "domains"
        / "routines"
        / "infrastructure"
        / "sqlalchemy_daily_activity_plans.py": {
            "prepare_activity_plan",
            "get_activity_plan",
            "update_activity_runtime_mode",
        },
        APP_ROOT / "domains" / "routines" / "public.py": {
            "reconcile_all_elapsed_routines",
        },
        APP_ROOT
        / "domains"
        / "routine_posts"
        / "infrastructure"
        / "sqlalchemy_runtime.py": {
            "run_routine_post_runtime",
        },
        APP_ROOT / "services" / "community.py": {
            "create_post",
            "create_reply",
        },
    }

    for path, functions in expected.items():
        assert path.is_file(), path
        assert functions <= _function_names(path)


def test_world_creator_route_uses_worlds_public_boundary() -> None:
    route = APP_ROOT / "api" / "v1" / "routes" / "worlds.py"
    imports = _imports(route)

    assert "app.domains.worlds" in imports
    assert "app.services.worlds" not in imports


def test_autonomous_setup_routes_use_world_characters_public_boundary() -> None:
    for route_name in ("worlds.py", "world_character_setup.py"):
        route = APP_ROOT / "api" / "v1" / "routes" / route_name
        imports = _imports(route)

        assert "app.domains.world_characters" in imports
        assert "app.services.world_character_setup" not in imports


def test_activity_plan_route_and_scheduler_use_routines_public_boundary() -> None:
    route = APP_ROOT / "api" / "v1" / "routes" / "world_activity_runtime.py"
    agent_runs = APP_ROOT / "services" / "agent_runs.py"
    resident = APP_ROOT / "services" / "langgraph_resident.py"

    assert "app.domains.routines" in _imports(route)
    assert "app.services.daily_activity_plans" not in _imports(route)
    assert "app.domains.routines.public" in _imports(agent_runs)
    assert "app.domains.routine_posts.public" in _imports(agent_runs)
    assert "app.services.routine_post_runtime" not in _imports(agent_runs)
    assert "app.domains.routine_posts.public" in _imports(resident)
    assert "app.services.routine_post_runtime" not in _imports(resident)


def test_daily_plan_legacy_path_is_a_thin_domain_facade() -> None:
    facade = APP_ROOT / "services" / "daily_activity_plans.py"
    imports = _imports(facade)

    assert imports == {"app.domains.routines.public"}
    assert not _function_names(facade)


def test_l3_public_package_anchors_have_no_reverse_dependencies() -> None:
    forbidden_prefixes = (
        "app.api",
        "app.integrations",
        "app.models",
        "app.runtime",
        "app.schemas",
        "app.services",
        "fastapi",
        "sqlalchemy",
    )

    for boundary in PUBLIC_BOUNDARIES:
        path = APP_ROOT / "domains" / boundary / "public.py"
        assert path.is_file(), path
        imports = _imports(path)
        assert not {
            imported
            for imported in imports
            if imported in forbidden_prefixes
            or imported.startswith(tuple(f"{prefix}." for prefix in forbidden_prefixes))
        }
