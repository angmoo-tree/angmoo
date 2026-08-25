"""Forward-only v1 to v2 World Package registry migration."""

from __future__ import annotations

from sqlalchemy import Connection

from app.runtime.persistence.sqlite_schema import (
    WORLD_PACKAGE_REGISTRY_TABLES,
    build_sqlite_baseline_metadata,
)


def upgrade_v1_to_v2(connection: Connection) -> None:
    metadata = build_sqlite_baseline_metadata()
    metadata.create_all(
        connection,
        tables=[metadata.tables[name] for name in WORLD_PACKAGE_REGISTRY_TABLES],
        checkfirst=False,
    )


__all__ = ["upgrade_v1_to_v2"]
