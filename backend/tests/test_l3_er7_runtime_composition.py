from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.v1.routes import world_activity_runtime
from app.core.config import Settings
from app.public_main import create_app
from app.runtime.configuration import (
    RuntimeConfigurationError,
    RuntimeProfile,
    build_embedded_runtime_config,
    compose_runtime,
    settings_from_runtime_config,
)
from app.runtime.contributor_backend import create_contributor_runtime_app


ROOT = Path(__file__).resolve().parents[2]


def _write_secret(data_root: Path) -> None:
    secret = data_root / "secrets" / "app-secret"
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text("synthetic-er7-secret\n", encoding="utf-8")


def _embedded_config(
    tmp_path: Path,
    *,
    profile: RuntimeProfile = RuntimeProfile.LOCAL_EMBEDDED,
    name: str = "product",
):
    data_root = tmp_path / name
    _write_secret(data_root)
    return build_embedded_runtime_config(
        profile=profile,
        data_root=data_root,
        runtime_root=data_root / "runtime",
        generation="er7-canonical-v1",
        desktop_launch_token="a" * 32,
        desktop_allowed_origin="http://tauri.localhost",
    )


def test_runtime_profile_is_closed_to_the_three_sqlite_only_values() -> None:
    assert tuple(profile.value for profile in RuntimeProfile) == (
        "LOCAL_EMBEDDED",
        "CONTRIBUTOR_EMBEDDED",
        "TEST",
    )
    assert RuntimeProfile.parse("contributor_embedded") is (
        RuntimeProfile.CONTRIBUTOR_EMBEDDED
    )
    for invalid in (None, "", "DOCKER_COMPATIBILITY", "POSTGRESQL"):
        with pytest.raises(RuntimeConfigurationError):
            RuntimeProfile.parse(invalid)


def test_poisoned_parent_environment_cannot_change_embedded_composition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    poison = {
        "DATABASE_URL": "postgresql+psycopg://poison/angmoo",
        "NEO4J_URI": "bolt://poison.invalid:7687",
        "GRAPH_PROVIDER": "neo4j",
        "GRAPH_PROJECTION_ENABLED": "false",
        "LOCAL_RUNTIME_COMPONENT_MODE": "external",
        "LADYBUG_DATABASE_ROOT": str(tmp_path / "poison-graph"),
    }
    for key, value in poison.items():
        monkeypatch.setenv(key, value)
    before = {key: __import__("os").environ[key] for key in poison}

    product = _embedded_config(tmp_path, name="product")
    contributor = _embedded_config(
        tmp_path,
        profile=RuntimeProfile.CONTRIBUTOR_EMBEDDED,
        name="contributor",
    )
    neutral_base = Settings(
        _env_file=None,
        DATABASE_URL="sqlite+pysqlite:///neutral.sqlite3",
        GRAPH_PROVIDER="ladybug",
        GRAPH_PROJECTION_ENABLED=True,
        LOCAL_RUNTIME_COMPONENT_MODE="in_process",
        LADYBUG_DATABASE_ROOT=str(tmp_path / "neutral-graph"),
    )
    product_settings = settings_from_runtime_config(product, base=neutral_base)
    contributor_settings = settings_from_runtime_config(
        contributor,
        base=neutral_base,
    )

    for config, resolved in (
        (product, product_settings),
        (contributor, contributor_settings),
    ):
        assert resolved.database_url == config.database_url
        assert resolved.database_url.startswith("sqlite+pysqlite:///")
        assert resolved.graph_provider == "ladybug"
        assert resolved.LOCAL_RUNTIME_COMPONENT_MODE == "in_process"
        assert resolved.ladybug_database_root == config.graph_database_root
    assert product_settings.app_env == "local"
    assert contributor_settings.app_env == "development"
    assert product.data_paths.root != contributor.data_paths.root
    assert {key: __import__("os").environ[key] for key in poison} == before


def test_create_app_owns_explicit_embedded_session_and_runtime_state(
    tmp_path: Path,
) -> None:
    config = _embedded_config(tmp_path)
    composition = compose_runtime(config, base_settings=Settings(_env_file=None))
    composition.dispose()

    app = create_app(runtime_config=config)
    try:
        assert app.state.runtime_config is config
        assert app.state.runtime_settings.database_url == config.database_url
        assert app.state.runtime_settings.graph_provider == "ladybug"
        assert app.state.runtime_composition.session_factory.kw["bind"] is (
            app.state.runtime_composition.engine
        )
    finally:
        app.state.restore_process_settings()


def test_typed_runtime_materializes_secret_and_media_for_legacy_service_refs(
    tmp_path: Path,
) -> None:
    from app.core.config import settings

    config = _embedded_config(tmp_path)
    app = create_app(runtime_config=config)
    try:
        assert settings.app_secret == "synthetic-er7-secret"
        assert settings.media_root_path == config.data_paths.media.resolve()
        assert (config.data_paths.media / "characters").is_dir()
        assert (config.data_paths.media / "posts").is_dir()
    finally:
        app.state.restore_process_settings()


def test_public_composition_import_does_not_load_postgres_dbapi() -> None:
    script = """
import builtins

original_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if name == "psycopg" or name.startswith("psycopg."):
        raise ImportError("packaged sidecar excludes psycopg")
    return original_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
import app.public_main  # noqa: F401
from app.core import db

assert db._default_engine is None
assert db._default_session_factory is None
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_contributor_entrypoint_uses_an_explicit_isolated_data_root(
    tmp_path: Path,
) -> None:
    contributor_root = tmp_path / "checkout-a" / ".angmoo-dev"
    app = create_contributor_runtime_app(data_root=contributor_root)
    with TestClient(app) as client:
        config = app.state.runtime_config
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "profile": "CONTRIBUTOR_EMBEDDED",
            "persistence": "sqlite",
            "graph": "ladybug",
            "components": {"scheduler": "ready", "projector": "ready"},
        }
        assert config.profile is RuntimeProfile.CONTRIBUTOR_EMBEDDED
        assert config.data_paths.root == contributor_root.resolve()
        assert app.state.runtime_settings.app_env == "development"
        assert app.state.runtime_settings.graph_provider == "ladybug"
        assert config.database_path.is_file()
        assert config.app_secret_file.is_file()


def test_contributor_diagnostics_registers_all_models_in_a_fresh_process(
    tmp_path: Path,
) -> None:
    contributor_root = tmp_path / "diagnostics" / ".angmoo-dev"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.runtime.contributor_backend",
            "--data-root",
            str(contributor_root),
            "--diagnostics",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["runtime_profile"] == "CONTRIBUTOR_EMBEDDED"
    assert payload["persistence_provider"] == "sqlite"
    assert payload["graph_provider"] == "ladybug"
    assert (
        contributor_root
        / "canonical"
        / "generations"
        / "contributor-v1"
        / "angmoo.sqlite3"
    ).is_file()


def test_relationship_route_uses_runtime_provider_when_query_is_omitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _embedded_config(tmp_path)
    runtime_settings = settings_from_runtime_config(
        config,
        base=Settings(_env_file=None),
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(runtime_settings=runtime_settings))
    )
    observed: dict[str, object] = {}

    class Gateway:
        def __init__(self, _db, *, config, graph_provider) -> None:
            observed["gateway_config"] = config
            observed["gateway_provider"] = graph_provider

    def fake_read(_gateway, **kwargs):
        observed.update(kwargs)
        return "ladybug-result"

    monkeypatch.setattr(
        world_activity_runtime,
        "SqlAlchemyRelationshipGraphReadGateway",
        Gateway,
    )
    monkeypatch.setattr(
        world_activity_runtime.relationships,
        "get_owner_relationship_graph",
        fake_read,
    )

    result = world_activity_runtime.get_world_character_relationship_graph(
        request,
        "character",
        "world",
        provider=None,
        db=object(),
        user=SimpleNamespace(id="owner"),
    )

    assert result == "ladybug-result"
    assert observed["gateway_config"] is runtime_settings
    assert observed["gateway_provider"] == "ladybug"
    assert observed["graph_provider"] == "ladybug"


def test_unknown_profile_does_not_create_database_or_secret(tmp_path: Path) -> None:
    data_root = tmp_path / "must-not-exist"

    with pytest.raises(RuntimeConfigurationError, match="runtime_profile_unknown"):
        profile = RuntimeProfile.parse("DOCKER_COMPATIBILITY")
        build_embedded_runtime_config(
            profile=profile,
            data_root=data_root,
            runtime_root=data_root / "runtime",
            generation="forbidden",
            desktop_launch_token="a" * 32,
            desktop_allowed_origin="http://tauri.localhost",
        )

    assert not data_root.exists()


def test_product_dependencies_exclude_server_database_runtimes() -> None:
    project = tomllib.loads(
        (ROOT / "backend/pyproject.toml").read_text(encoding="utf-8")
    )
    dependencies = tuple(project["project"]["dependencies"])
    optional_dependencies = project["project"].get("optional-dependencies", {})

    for forbidden in ("neo4j", "psycopg", "pgvector"):
        assert not any(forbidden in dependency.lower() for dependency in dependencies)
        assert not any(
            forbidden in dependency.lower()
            for group in optional_dependencies.values()
            for dependency in group
        )
    # Windows does not ship an IANA timezone database for Python's zoneinfo.
    # The packaged sidecar must therefore own tzdata explicitly rather than
    # inheriting it accidentally from a removed PostgreSQL dependency group.
    assert any(dependency.lower().startswith("tzdata") for dependency in dependencies)


def test_postgresql_offline_importer_is_removed_from_active_source() -> None:
    removed = (
        "backend/app/domains/runtime/ports/migration_source.py",
        "backend/app/domains/runtime/ports/offline_migration.py",
        "backend/app/runtime/migrations/alembic_source.py",
        "backend/app/runtime/migrations/postgres_to_sqlite.py",
        "backend/scripts/dry_run_postgres_to_sqlite.py",
        "backend/tests/test_l3_er2_postgres_sqlite_offline_migration.py",
        "backend/tests/test_l3_er6_postgres_installer_roundtrip.py",
    )

    for relative in removed:
        assert not (ROOT / relative).exists(), relative


def test_server_runtime_assets_and_external_worker_entrypoints_are_removed() -> None:
    removed = (
        "compose.neo4j.yml",
        "compose.in-process.yml",
        "scripts/docker/neo4j-entrypoint.sh",
        "scripts/docker/postgresql-entrypoint.sh",
        "backend/app/integrations/neo4j.py",
        "backend/scripts/run_graph_projection_worker.py",
        "backend/scripts/run_resident_tick_scheduler.py",
    )

    for relative in removed:
        assert not (ROOT / relative).exists(), relative

    compose = (ROOT / "compose.yml").read_text(encoding="utf-8")
    assert "angmoo_contributor_embedded_data" in compose
    assert "postgresql:" not in compose
    assert "neo4j:" not in compose
    assert "scheduler:" not in compose
    assert "projector:" not in compose
