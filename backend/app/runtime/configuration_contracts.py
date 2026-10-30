"""Runtime values and validation, independent of storage/worker composition."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from app.domains.runtime.contracts.data_paths import RuntimeDataPaths

class ServingRetentionOwner(Protocol):
    """Capability supplied by the serving process; diagnostics do not acquire it."""
    def close(self) -> None: ...

class RuntimeConfigurationError(RuntimeError):
    """Fail-closed error safe to expose through local diagnostics."""



class RuntimeProfile(StrEnum):
    EXPERIMENT_POSTGRESQL = "EXPERIMENT_POSTGRESQL"
    CONTRIBUTOR_POSTGRESQL = "CONTRIBUTOR_POSTGRESQL"
    LOCAL_POSTGRESQL = "LOCAL_POSTGRESQL"
    LOCAL_EMBEDDED = "LOCAL_EMBEDDED"
    CONTRIBUTOR_EMBEDDED = "CONTRIBUTOR_EMBEDDED"
    TEST = "TEST"

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



class RuntimeComponentMode(StrEnum):
    IN_PROCESS = "in_process"



@dataclass(frozen=True)
class RuntimeConfig:
    profile: RuntimeProfile
    data_paths: RuntimeDataPaths
    generation: str
    database_url: str = field(repr=False)
    app_secret_file: Path
    graph_provider: RuntimeGraphProvider
    graph_database_root: Path | None
    graph_projection_enabled: bool
    component_mode: RuntimeComponentMode
    desktop_allowed_origin: str
    desktop_launch_token: str = field(repr=False)
    api_docs_enabled: bool = False
    signup_enabled: bool = False
    seed_demo_data: bool = False
    validation_mode: bool = False
    # An acquired serving-process capability, never an environment preference.
    # Diagnostics and default factories leave it absent and cannot prune DBs.
    serving_retention_owner: ServingRetentionOwner | None = field(
        default=None, repr=False, compare=False,
    )

    def __post_init__(self) -> None:
        if not self.generation.strip():
            raise RuntimeConfigurationError("runtime_generation_required")
        if self.profile is RuntimeProfile.EXPERIMENT_POSTGRESQL:
            from app.runtime.postgresql_configuration import validate_experiment_config as validate_config
            validate_config(self)
        elif self.profile in {RuntimeProfile.CONTRIBUTOR_POSTGRESQL, RuntimeProfile.LOCAL_POSTGRESQL}:
            from app.runtime.postgresql_configuration import validate_postgresql_config as validate_config
            validate_config(self)
        elif not self.database_url.startswith("sqlite+pysqlite:///"):
            raise RuntimeConfigurationError("embedded_sqlite_required")
        if self.graph_provider is not RuntimeGraphProvider.LADYBUG:
            raise RuntimeConfigurationError("embedded_ladybug_required")
        if self.graph_database_root is None:
            raise RuntimeConfigurationError("embedded_graph_root_required")
        if self.component_mode is not RuntimeComponentMode.IN_PROCESS:
            raise RuntimeConfigurationError("embedded_components_required")
        if (
            self.profile in {RuntimeProfile.LOCAL_EMBEDDED, RuntimeProfile.LOCAL_POSTGRESQL}
            and (
                not self.desktop_launch_token
                or len(self.desktop_launch_token) < 32
            )
        ):
            raise RuntimeConfigurationError("desktop_launch_token_invalid")

    @property
    def database_path(self) -> Path:
        if self.profile in {RuntimeProfile.EXPERIMENT_POSTGRESQL, RuntimeProfile.CONTRIBUTOR_POSTGRESQL, RuntimeProfile.LOCAL_POSTGRESQL}:
            raise RuntimeConfigurationError("postgresql_has_no_sqlite_database_path")
        return (
            self.data_paths.canonical
            / "generations"
            / self.generation
            / "angmoo.sqlite3"
        )
