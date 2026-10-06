"""Independent write-only credentials bound to an actual World actor and purpose."""
from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class WorldCredential(Base):
    __tablename__ = "world_credentials"
    __table_args__ = (
        ForeignKeyConstraint(["world_character_id", "world_id"], ["world_characters.id", "world_characters.world_id"]),
        UniqueConstraint("owner_id", "world_id", "world_character_id", "purpose", name="uq_world_credential_purpose"),
        CheckConstraint("revision >= 1", name="ck_world_credential_revision"),
        CheckConstraint("purpose IN ('sns','image','chat','vision','consolidation','embedding')", name="ck_world_credential_purpose"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(24), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    thinking_level: Mapped[str | None] = mapped_column(String(8))
    encrypted_secret: Mapped[str | None] = mapped_column(Text)
    fingerprint: Mapped[str | None] = mapped_column(String(32))
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Original envelope scope remains separate from World authorization.
    aad_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    aad_purpose: Mapped[str] = mapped_column(String(40), nullable=False)


class WorldCredentialRevision(Base):
    """Immutable encrypted revision for admitted work; explicit delete removes it."""
    __tablename__ = "world_credential_revisions"
    credential_id: Mapped[str] = mapped_column(ForeignKey("world_credentials.id"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    thinking_level: Mapped[str | None] = mapped_column(String(8))
    encrypted_secret: Mapped[str | None] = mapped_column(Text)
    fingerprint: Mapped[str | None] = mapped_column(String(32))
    aad_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    aad_purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    __table_args__ = (CheckConstraint("revision >= 1", name="ck_world_credential_history_revision"),)
