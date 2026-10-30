"""Typed composition for Angmoo's official embedded runtime profiles.

Database, graph, and component selection is owned by this module.  Launch
tokens and dynamic ports remain lifecycle inputs; they are not profile
selectors.
"""

from __future__ import annotations

from app.runtime.configuration_contracts import (RuntimeConfigurationError, RuntimeProfile, RuntimeGraphProvider, RuntimeComponentMode, RuntimeConfig)
from app.runtime.composition_resources import RuntimeComposition
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.database import create_database_engine, create_session_factory
from app.domains.memory.service.recall import CanonicalRecallService
from app.domains.runtime.contracts.data_paths import RuntimeDataPaths
from app.runtime.memory.recall_projection import EmbeddedMemoryRecallProjection
from app.runtime.memory.recall_composition import canonical_recall_repository as SqlAlchemyCanonicalRecallRepository
from app.runtime.memory.sqlite_fts5_recall import SqliteMemoryRecallIndex, MemoryRecallIndexSettings
from app.runtime.memory.hybrid_runtime import MemoryHybridRuntime
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.search import (
    EmbeddedSocialSearchProjection,
    SqliteFts5SearchIndex,
)

if TYPE_CHECKING:
    from app.runtime.migrations.canonical_retention import ServingRetentionOwner












def _sqlite_url(path: Path) -> str:
    return "sqlite+pysqlite:///" + path.resolve().as_posix()


def build_embedded_runtime_config(
    *,
    profile: RuntimeProfile,
    data_root: Path,
    runtime_root: Path,
    generation: str,
    desktop_launch_token: str,
    desktop_allowed_origin: str,
    graph_database_root: Path | None = None,
    graph_projection_enabled: bool = True,
) -> RuntimeConfig:
    if profile not in {
        RuntimeProfile.LOCAL_EMBEDDED,
        RuntimeProfile.CONTRIBUTOR_EMBEDDED,
        RuntimeProfile.TEST,
    }:
        raise RuntimeConfigurationError("embedded_profile_required")
    paths = StaticRuntimeDataPath(data_root).resolve()
    if runtime_root.resolve() != paths.runtime:
        raise RuntimeConfigurationError("runtime_root_outside_product_data_root")
    secret_path = paths.secrets / "app-secret"
    if not secret_path.is_file():
        raise RuntimeConfigurationError("app_secret_missing")
    database_path = (
        paths.canonical / "generations" / generation / "angmoo.sqlite3"
    )
    return RuntimeConfig(
        profile=profile,
        data_paths=paths,
        generation=generation,
        database_url=_sqlite_url(database_path),
        app_secret_file=secret_path,
        graph_provider=RuntimeGraphProvider.LADYBUG,
        graph_database_root=(
            graph_database_root or paths.graph / "ladybug"
        ).resolve(),
        graph_projection_enabled=graph_projection_enabled,
        component_mode=RuntimeComponentMode.IN_PROCESS,
        desktop_allowed_origin=desktop_allowed_origin,
        desktop_launch_token=desktop_launch_token,
    )


def settings_from_runtime_config(
    config: RuntimeConfig,
    *,
    base: Settings | None = None,
) -> Settings:
    values = (base or Settings()).model_dump()
    app_env = {
        RuntimeProfile.LOCAL_EMBEDDED: "local",
        RuntimeProfile.CONTRIBUTOR_EMBEDDED: "development",
        RuntimeProfile.TEST: "test",
        RuntimeProfile.EXPERIMENT_POSTGRESQL: "development",
        RuntimeProfile.CONTRIBUTOR_POSTGRESQL: "development",
        RuntimeProfile.LOCAL_POSTGRESQL: "local",
    }[config.profile]
    values.update(
        {
            "APP_ENV": app_env,
            "APP_SECRET_FILE": str(config.app_secret_file),
            "API_DOCS_ENABLED": config.api_docs_enabled,
            "SIGNUP_ENABLED": config.signup_enabled,
            "SEED_DEMO_DATA": config.seed_demo_data,
            "BROWSER_SESSION_ALLOWED_ORIGINS": config.desktop_allowed_origin,
            "DESKTOP_ALLOWED_ORIGIN": config.desktop_allowed_origin,
            "DESKTOP_LAUNCH_TOKEN": config.desktop_launch_token,
            "CREDENTIAL_ENCRYPTION_PROVIDER": "local",
            "DATABASE_URL": config.database_url,
            "MEDIA_ROOT": str(config.data_paths.media),
            "GRAPH_PROJECTION_ENABLED": config.graph_projection_enabled,
            "GRAPH_PROVIDER": config.graph_provider.value,
            "LADYBUG_DATABASE_ROOT": str(config.graph_database_root),
            "LOCAL_RUNTIME_COMPONENT_MODE": config.component_mode.value,
            "RESIDENT_TICK_PROCESS_LOCK_PATH": str(
                config.data_paths.runtime / "scheduler.lock"
            ),
            "RESIDENT_TICK_READY_PATH": str(
                config.data_paths.runtime / "scheduler.ready"
            ),
            "GRAPH_PROJECTOR_READY_PATH": str(
                config.data_paths.runtime / "projector.ready"
            ),
        }
    )
    return Settings(**values)




def compose_runtime(
    config: RuntimeConfig,
    *,
    base_settings: Settings | None = None,
) -> RuntimeComposition:
    runtime_settings = settings_from_runtime_config(config, base=base_settings)
    if config.profile in {RuntimeProfile.EXPERIMENT_POSTGRESQL, RuntimeProfile.CONTRIBUTOR_POSTGRESQL, RuntimeProfile.LOCAL_POSTGRESQL}:
        from app.runtime.postgresql_runtime import compose
        return compose(config, runtime_settings)
    from app.runtime.migrations.canonical_retention import GenerationUsePin
    pin = GenerationUsePin(config.data_paths.root, f"generations/{config.generation}").acquire()
    engine = None
    try:
        engine = create_database_engine(runtime_settings.database_url)
        # Sessions/workers keep the engine alive. If shutdown cannot confirm
        # all workers stopped, retain its OS use lock for that same lifetime.
        engine._angmoo_generation_use_pin = pin
        session_factory = create_session_factory(engine)
        data_paths = StaticRuntimeDataPath(config.data_paths.root)
        episode_only = runtime_settings.MEMORY_RECALL_REPRESENTATION == "episode_v1"
        memory_recall_index = SqliteMemoryRecallIndex(
            data_paths,
            settings=MemoryRecallIndexSettings.for_representation(
                runtime_settings.MEMORY_RECALL_REPRESENTATION
            ),
        )
        memory_hybrid_runtime = MemoryHybridRuntime(session_factory, memory_recall_index, data_paths.resolve(),
            fts_policy=runtime_settings.CHAT_HYBRID_FTS_POLICY, episode_only=episode_only)
        return RuntimeComposition(
            config=config,
            settings=runtime_settings,
            engine=engine,
            session_factory=session_factory,
            social_search_projection=EmbeddedSocialSearchProjection(
                index=SqliteFts5SearchIndex(data_paths),
                session_factory=session_factory,
            ),
            memory_recall_projection=EmbeddedMemoryRecallProjection(
                index=memory_recall_index,
                session_factory=session_factory,
                episode_only=episode_only,
            ),
            memory_recall_service=CanonicalRecallService(
                SqlAlchemyCanonicalRecallRepository(session_factory),
                memory_recall_index,
                hybrid_service=memory_hybrid_runtime.service,
            ),
            memory_hybrid_runtime=memory_hybrid_runtime,
            generation_use_pin=pin,
        )
    except BaseException:
        if engine is not None:
            engine.dispose()
        pin.close()
        raise


def initialize_local_installation_identity(
    session_factory: sessionmaker[Session],
) -> None:
    """Ensure the singleton device identity before in-process workers start."""

    from app.domains.identity.service.local_owner import LocalIdentityService

    with session_factory() as db:
        LocalIdentityService(db).ensure_local_installation_identity()


__all__ = [
    "RuntimeComponentMode",
    "RuntimeComposition",
    "RuntimeConfig",
    "RuntimeConfigurationError",
    "RuntimeGraphProvider",
    "RuntimeProfile",
    "build_embedded_runtime_config",
    "compose_runtime",
    "initialize_local_installation_identity",
    "settings_from_runtime_config",
]
