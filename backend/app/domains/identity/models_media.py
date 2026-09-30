"""Purpose-scoped image credentials, independent of the one-to-one LLM key."""
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


class MediaCredential(Base):
    __tablename__ = "media_credentials"
    __table_args__ = (UniqueConstraint("owner_id", "character_scope", "provider", "purpose", name="uq_media_credential_scope"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    character_scope: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default="")
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    encrypted_secret: Mapped[str | None] = mapped_column(Text)
    fingerprint: Mapped[str | None] = mapped_column(String(32))
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
