"""SQLite-first lineage registry for World Package v1."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class WorldPackageSource(Base):
    __tablename__ = "world_package_sources"
    __table_args__ = (
        CheckConstraint("next_version >= 1", name="ck_world_package_sources_version"),
        UniqueConstraint("source_world_id", name="uq_world_package_sources_world"),
    )

    package_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_world_id: Mapped[str] = mapped_column(
        ForeignKey("worlds.id"), nullable=False
    )
    next_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WorldPackageExport(Base):
    __tablename__ = "world_package_exports"
    __table_args__ = (
        CheckConstraint("package_version >= 1", name="ck_world_package_exports_version"),
        CheckConstraint(
            "delivery_mode IN ('browser_download','tauri_save_as')",
            name="ck_world_package_exports_delivery_mode",
        ),
        UniqueConstraint(
            "package_id",
            "package_version",
            name="uq_world_package_exports_version",
        ),
        Index("ix_world_package_exports_source", "source_world_id", "created_at"),
    )

    export_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    package_id: Mapped[str] = mapped_column(
        ForeignKey("world_package_sources.package_id"), nullable=False
    )
    package_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_world_id: Mapped[str] = mapped_column(
        ForeignKey("worlds.id"), nullable=False
    )
    seed_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    license_expression: Mapped[str] = mapped_column(String(160), nullable=False)
    delivery_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorldPackageImport(Base):
    __tablename__ = "world_package_imports"
    __table_args__ = (
        CheckConstraint("package_version >= 1", name="ck_world_package_imports_version"),
        CheckConstraint(
            "import_mode IN ('new_world')",
            name="ck_world_package_imports_mode",
        ),
        CheckConstraint(
            "trust_state IN ('locally_exported','checksum_verified_unsigned')",
            name="ck_world_package_imports_trust",
        ),
        UniqueConstraint(
            "local_owner_id",
            "idempotency_key",
            name="uq_world_package_imports_owner_request",
        ),
        Index("ix_world_package_imports_package", "package_id", "package_version"),
        Index("ix_world_package_imports_owner", "local_owner_id", "imported_at"),
    )

    import_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    local_owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    package_id: Mapped[str] = mapped_column(String(64), nullable=False)
    package_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    imported_world_id: Mapped[str] = mapped_column(
        ForeignKey("worlds.id"), nullable=False, unique=True
    )
    import_mode: Mapped[str] = mapped_column(
        String(24), nullable=False, default="new_world"
    )
    trust_state: Mapped[str] = mapped_column(String(40), nullable=False)
    license_expression: Mapped[str] = mapped_column(String(160), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorldPackageImportIdMap(Base):
    __tablename__ = "world_package_import_id_maps"
    __table_args__ = (
        CheckConstraint(
            "entity_kind IN ('world','character','world_character','asset')",
            name="ck_world_package_import_id_maps_kind",
        ),
        UniqueConstraint(
            "import_id",
            "source_ref",
            name="uq_world_package_import_id_maps_source",
        ),
        UniqueConstraint(
            "import_id",
            "entity_kind",
            "local_id",
            name="uq_world_package_import_id_maps_local",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    import_id: Mapped[str] = mapped_column(
        ForeignKey("world_package_imports.import_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_ref: Mapped[str] = mapped_column(String(240), nullable=False)
    entity_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    local_id: Mapped[str] = mapped_column(String(500), nullable=False)


__all__ = [
    "WorldPackageExport",
    "WorldPackageImport",
    "WorldPackageImportIdMap",
    "WorldPackageSource",
]
