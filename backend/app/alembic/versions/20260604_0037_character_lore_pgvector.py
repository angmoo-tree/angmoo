"""add character lore pgvector storage

Revision ID: 20260604_0037
Revises: 20260601_0036
Create Date: 2026-06-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector


revision: str = "20260604_0037"
down_revision: Union[str, None] = "20260601_0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "character_lore_sources",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("character_id", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=240), nullable=False),
        sa.Column("extension", sa.String(length=12), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("raw_text_hash", sa.String(length=64), nullable=False),
        sa.Column("extracted_char_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('ready', 'partial', 'embedding_failed')",
            name="ck_character_lore_sources_status",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "character_id",
            "raw_text_hash",
            name="uq_character_lore_sources_character_raw_hash",
        ),
    )
    op.create_index(
        "ix_character_lore_sources_character_id",
        "character_lore_sources",
        ["character_id"],
    )
    op.create_index(
        "ix_character_lore_sources_owner_id",
        "character_lore_sources",
        ["owner_id"],
    )
    op.create_table(
        "character_lore_chunks",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("character_id", sa.String(length=64), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("section_hint", sa.String(length=200), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column("embedding_model", sa.String(length=80), nullable=True),
        sa.Column("embedding_dimension", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('ready', 'embedding_failed')",
            name="ck_character_lore_chunks_status",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["character_lore_sources.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_character_lore_chunks_character_status",
        "character_lore_chunks",
        ["character_id", "status"],
    )
    op.create_index(
        "ix_character_lore_chunks_source_id",
        "character_lore_chunks",
        ["source_id"],
    )
    op.create_index(
        "ix_character_lore_chunks_content_hash",
        "character_lore_chunks",
        ["character_id", "content_hash"],
    )
    op.execute(
        "CREATE INDEX ix_character_lore_chunks_embedding_hnsw "
        "ON character_lore_chunks "
        "USING hnsw (embedding vector_cosine_ops) "
        "WHERE embedding IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_character_lore_chunks_embedding_hnsw")
    op.drop_index("ix_character_lore_chunks_content_hash", table_name="character_lore_chunks")
    op.drop_index("ix_character_lore_chunks_source_id", table_name="character_lore_chunks")
    op.drop_index(
        "ix_character_lore_chunks_character_status",
        table_name="character_lore_chunks",
    )
    op.drop_table("character_lore_chunks")
    op.drop_index("ix_character_lore_sources_owner_id", table_name="character_lore_sources")
    op.drop_index(
        "ix_character_lore_sources_character_id",
        table_name="character_lore_sources",
    )
    op.drop_table("character_lore_sources")
