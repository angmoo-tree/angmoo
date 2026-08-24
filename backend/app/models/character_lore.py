from datetime import datetime
import json
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class EmbeddingJsonText(TypeDecorator[list[float] | None]):
    """Persist embeddings as deterministic JSON inside the existing TEXT column.

    ER2 froze the SQLite physical schema with ``embedding`` as TEXT.  Keeping
    the storage type stable avoids an unnecessary generation migration while
    removing the PostgreSQL/pgvector runtime dependency.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):  # type: ignore[no-untyped-def]
        del dialect
        if value is None:
            return None
        return json.dumps([float(item) for item in value], separators=(",", ":"))

    def process_result_value(self, value, dialect):  # type: ignore[no-untyped-def]
        del dialect
        if value is None or isinstance(value, list):
            return value
        parsed = json.loads(value)
        if not isinstance(parsed, list):
            raise ValueError("character_lore_embedding_not_a_list")
        return [float(item) for item in parsed]


class CharacterLoreSource(Base):
    __tablename__ = "character_lore_sources"
    __table_args__ = (
        CheckConstraint(
            "status in ('ready', 'partial', 'embedding_failed')",
            name="ck_character_lore_sources_status",
        ),
        UniqueConstraint(
            "character_id",
            "raw_text_hash",
            name="uq_character_lore_sources_character_raw_hash",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(240), nullable=False)
    extension: Mapped[str] = mapped_column(String(12), nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    raw_text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    extracted_char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="ready")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    chunks: Mapped[list["CharacterLoreChunk"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class CharacterLoreChunk(Base):
    __tablename__ = "character_lore_chunks"
    __table_args__ = (
        CheckConstraint(
            "status in ('ready', 'embedding_failed')",
            name="ck_character_lore_chunks_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("character_lore_sources.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section_hint: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Embeddings are canonical payload, not a database-specific vector index.
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        EmbeddingJsonText(), nullable=True
    )
    embedding_model: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    embedding_dimension: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="embedding_failed"
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    source: Mapped[CharacterLoreSource] = relationship(back_populates="chunks")


class LoreParserLease(Base):
    __tablename__ = "lore_parser_leases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    lease_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    released_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
