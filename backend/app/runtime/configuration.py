"""Typed composition for Angmoo's official embedded runtime profiles.

Database, graph, and component selection is owned by this module.  Launch
tokens and dynamic ports remain lifecycle inputs; they are not profile
selectors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.db import create_database_engine, create_session_factory
from app.domains.runtime.ports.runtime_data_path import RuntimeDataPaths
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath


class RuntimeConfigurationError(RuntimeError):
    """Fail-closed error safe to expose through local diagnostics."""


class RuntimeProfile(StrEnum):
    LOCAL_EMBEDDED = "LOCAL_EMBEDDED"
    CONTRIBUTOR_EMBEDDED = "CONTRIBUTOR_EMBEDDED"
    TEST = "TEST"
    LEGACY_MIGRATION = "LEGACY_MIGRATION"

    @classmethod
    def parse(cls, value: str | None) -> "RuntimeProfile":
        if value is None or not value.strip():
            raise RuntimeConfigurationError("runtime_profile_required")
        try:
            return cls(value.strip().upper())
        except ValueError as exc:
            raise RuntimeConfigurationError("runtime_profile_unknown") from exc


class RuntimeGraphProvider(StrEnum):
    LADYBUG = "ladybug"
    NONE = "none"


class RuntimeComponentMode(StrEnum):
    IN_PROCESS = "in_process"
    DISABLED = "disabled"


@dataclass(frozen=True)
class RuntimeConfig:
    profile: RuntimeProfile
    data_paths: RuntimeDataPaths
    generation: str
    database_url: str
    app_secret_file: Path
    graph_provider: RuntimeGraphProvider
    graph_database_root: Path | None
    component_mode: RuntimeComponentMode
    desktop_allowed_origin: str
    desktop_launch_token: str = field(repr=False)
    api_docs_enabled: bool = False
    signup_enabled: bool = False
    seed_demo_data: bool = False
    public_runtime_enabled: bool = True
    source_database_url: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.generation.strip():
            raise RuntimeConfigurationError("runtime_generation_required")
        if self.profile is RuntimeProfile.LEGACY_MIGRATION:
            if self.public_runtime_enabled:
                raise RuntimeConfigurationError("legacy_public_runtime_forbidden")
            if self.component_mode is not RuntimeComponentMode.DISABLED:
                raise RuntimeConfigurationError("legacy_components_forbidden")
            if self.graph_provider is not RuntimeGraphProvider.NONE:
                raise RuntimeConfigurationError("legacy_graph_forbidden")
            if not self.source_database_url:
                raise RuntimeConfigurationError("legacy_source_required")
            return
        if not self.database_url.startswith("sqlite+pysqlite:///"):
            raise RuntimeConfigurationError("embedded_sqlite_required")
        if self.graph_provider is not RuntimeGraphProvider.LADYBUG:
            raise RuntimeConfigurationError("embedded_ladybug_required")
        if self.graph_database_root is None:
            raise RuntimeConfigurationError("embedded_graph_root_required")
        if self.component_mode is not RuntimeComponentMode.IN_PROCESS:
            raise RuntimeConfigurationError("embedded_components_required")
        if (
            self.profile is RuntimeProfile.LOCAL_EMBEDDED
            and (
                not self.desktop_launch_token
                or len(self.desktop_launch_token) < 32
            )
        ):
            raise RuntimeConfigurationError("desktop_launch_token_invalid")

    @property
    def database_path(self) -> Path:
        return (
            self.data_paths.canonical
            / "generations"
            / self.generation
            / "angmoo.sqlite3"
        )

    def require_public_runtime(self) -> None:
        if not self.public_runtime_enabled:
            raise RuntimeConfigurationError("runtime_public_surface_forbidden")


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
        graph_database_root=paths.graph / "ladybug",
        component_mode=RuntimeComponentMode.IN_PROCESS,
        desktop_allowed_origin=desktop_allowed_origin,
        desktop_launch_token=desktop_launch_token,
    )


def build_legacy_migration_runtime_config(
    *,
    source_database_url: str,
    target_root: Path,
) -> RuntimeConfig:
    paths = StaticRuntimeDataPath(target_root).resolve()
    if not source_database_url.startswith("postgresql"):
        raise RuntimeConfigurationError("legacy_postgresql_source_required")
    return RuntimeConfig(
        profile=RuntimeProfile.LEGACY_MIGRATION,
        data_paths=paths,
        generation="legacy-import",
        database_url="",
        app_secret_file=paths.secrets / "app-secret",
        graph_provider=RuntimeGraphProvider.NONE,
        graph_database_root=None,
        component_mode=RuntimeComponentMode.DISABLED,
        desktop_allowed_origin="",
        desktop_launch_token="",
        public_runtime_enabled=False,
        source_database_url=source_database_url,
    )


def settings_from_runtime_config(
    config: RuntimeConfig,
    *,
    base: Settings | None = None,
) -> Settings:
    config.require_public_runtime()
    values = (base or Settings()).model_dump()
    app_env = {
        RuntimeProfile.LOCAL_EMBEDDED: "local",
        RuntimeProfile.CONTRIBUTOR_EMBEDDED: "development",
        RuntimeProfile.TEST: "test",
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
            "GRAPH_PROJECTION_ENABLED": True,
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


@dataclass(frozen=True)
class RuntimeComposition:
    config: RuntimeConfig
    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]

    def dispose(self) -> None:
        self.engine.dispose()


def compose_runtime(
    config: RuntimeConfig,
    *,
    base_settings: Settings | None = None,
) -> RuntimeComposition:
    runtime_settings = settings_from_runtime_config(config, base=base_settings)
    engine = create_database_engine(runtime_settings.database_url)
    return RuntimeComposition(
        config=config,
        settings=runtime_settings,
        engine=engine,
        session_factory=create_session_factory(engine),
    )


def initialize_local_installation_identity(
    session_factory: sessionmaker[Session],
) -> None:
    """Ensure the singleton device identity before in-process workers start."""

    from app.domains.identity.application.local_owner import (
        EnsureLocalInstallationIdentity,
    )
    from app.domains.identity.infrastructure.sqlalchemy_identity_repository import (
        SqlAlchemyIdentityRepository,
    )

    with session_factory() as db:
        EnsureLocalInstallationIdentity(
            SqlAlchemyIdentityRepository(db)
        ).execute()


__all__ = [
    "RuntimeComponentMode",
    "RuntimeComposition",
    "RuntimeConfig",
    "RuntimeConfigurationError",
    "RuntimeGraphProvider",
    "RuntimeProfile",
    "build_embedded_runtime_config",
    "build_legacy_migration_runtime_config",
    "compose_runtime",
    "initialize_local_installation_identity",
    "settings_from_runtime_config",
]
