"""Provider vault, separate from the currently selected execution revision."""
from sqlalchemy import Boolean, CheckConstraint, ForeignKey, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


class WorldImageProviderCredential(Base):
    __tablename__ = "world_image_provider_credentials"
    __table_args__ = (
        ForeignKeyConstraint(["world_character_id", "world_id"], ["world_characters.id", "world_characters.world_id"]),
        UniqueConstraint("owner_id", "world_id", "world_character_id", "provider", "purpose", name="uq_world_image_provider_scope"),
        CheckConstraint("revision >= 1", name="ck_world_image_provider_revision"),
        CheckConstraint("(purpose='user_image' AND provider IN ('novelai','nanogpt','openrouter')) OR (purpose='comfy_partner_image' AND provider='comfyui')", name="ck_world_image_provider_purpose"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    encrypted_secret: Mapped[str | None] = mapped_column(Text)
    fingerprint: Mapped[str | None] = mapped_column(String(32))
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tombstone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    aad_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    aad_purpose: Mapped[str] = mapped_column(String(40), nullable=False)
