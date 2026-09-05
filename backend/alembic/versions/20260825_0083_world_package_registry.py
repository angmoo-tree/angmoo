"""add World Package v1 lineage registry

Revision ID: 20260825_0083
Revises: 20260819_0082
Create Date: 2026-08-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260825_0083"
down_revision: str | None = "20260819_0082"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "world_package_sources",
        sa.Column("package_id", sa.String(length=64), nullable=False),
        sa.Column("source_world_id", sa.String(length=64), nullable=False),
        sa.Column("next_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("next_version >= 1", name="ck_world_package_sources_version"),
        sa.ForeignKeyConstraint(["source_world_id"], ["worlds.id"]),
        sa.PrimaryKeyConstraint("package_id"),
        sa.UniqueConstraint("source_world_id", name="uq_world_package_sources_world"),
    )
    op.create_table(
        "world_package_exports",
        sa.Column("export_id", sa.String(length=64), nullable=False),
        sa.Column("package_id", sa.String(length=64), nullable=False),
        sa.Column("package_version", sa.Integer(), nullable=False),
        sa.Column("source_world_id", sa.String(length=64), nullable=False),
        sa.Column("seed_digest", sa.String(length=64), nullable=False),
        sa.Column("manifest_digest", sa.String(length=64), nullable=False),
        sa.Column("license_expression", sa.String(length=160), nullable=False),
        sa.Column("delivery_mode", sa.String(length=32), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("package_version >= 1", name="ck_world_package_exports_version"),
        sa.CheckConstraint("delivery_mode IN ('browser_download','tauri_save_as')", name="ck_world_package_exports_delivery_mode"),
        sa.ForeignKeyConstraint(["package_id"], ["world_package_sources.package_id"]),
        sa.ForeignKeyConstraint(["source_world_id"], ["worlds.id"]),
        sa.PrimaryKeyConstraint("export_id"),
        sa.UniqueConstraint("package_id", "package_version", name="uq_world_package_exports_version"),
    )
    op.create_index("ix_world_package_exports_source", "world_package_exports", ["source_world_id", "created_at"])
    op.create_table(
        "world_package_imports",
        sa.Column("import_id", sa.String(length=64), nullable=False),
        sa.Column("local_owner_id", sa.String(length=64), nullable=False),
        sa.Column("package_id", sa.String(length=64), nullable=False),
        sa.Column("package_version", sa.Integer(), nullable=False),
        sa.Column("content_digest", sa.String(length=64), nullable=False),
        sa.Column("imported_world_id", sa.String(length=64), nullable=False),
        sa.Column("import_mode", sa.String(length=24), nullable=False),
        sa.Column("trust_state", sa.String(length=40), nullable=False),
        sa.Column("license_expression", sa.String(length=160), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("package_version >= 1", name="ck_world_package_imports_version"),
        sa.CheckConstraint("import_mode IN ('new_world')", name="ck_world_package_imports_mode"),
        sa.CheckConstraint("trust_state IN ('locally_exported','checksum_verified_unsigned')", name="ck_world_package_imports_trust"),
        sa.ForeignKeyConstraint(["imported_world_id"], ["worlds.id"]),
        sa.ForeignKeyConstraint(["local_owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("import_id"),
        sa.UniqueConstraint("imported_world_id"),
        sa.UniqueConstraint("local_owner_id", "idempotency_key", name="uq_world_package_imports_owner_request"),
    )
    op.create_index("ix_world_package_imports_owner", "world_package_imports", ["local_owner_id", "imported_at"])
    op.create_index("ix_world_package_imports_package", "world_package_imports", ["package_id", "package_version"])
    op.create_table(
        "world_package_import_id_maps",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("import_id", sa.String(length=64), nullable=False),
        sa.Column("source_ref", sa.String(length=240), nullable=False),
        sa.Column("entity_kind", sa.String(length=32), nullable=False),
        sa.Column("local_id", sa.String(length=500), nullable=False),
        sa.CheckConstraint("entity_kind IN ('world','character','world_character','asset')", name="ck_world_package_import_id_maps_kind"),
        sa.ForeignKeyConstraint(["import_id"], ["world_package_imports.import_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("import_id", "entity_kind", "local_id", name="uq_world_package_import_id_maps_local"),
        sa.UniqueConstraint("import_id", "source_ref", name="uq_world_package_import_id_maps_source"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in (
        "world_package_import_id_maps",
        "world_package_imports",
        "world_package_exports",
        "world_package_sources",
    ):
        count = bind.scalar(sa.text(f"SELECT count(*) FROM {table_name}"))
        if int(count or 0) > 0:
            raise RuntimeError(
                f"cannot downgrade 0083 while {table_name} contains package lineage"
            )
    op.drop_table("world_package_import_id_maps")
    op.drop_index("ix_world_package_imports_package", table_name="world_package_imports")
    op.drop_index("ix_world_package_imports_owner", table_name="world_package_imports")
    op.drop_table("world_package_imports")
    op.drop_index("ix_world_package_exports_source", table_name="world_package_exports")
    op.drop_table("world_package_exports")
    op.drop_table("world_package_sources")
