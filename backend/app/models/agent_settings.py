from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core import active_hours
from app.core.db import Base
from app.core.image_generation import (
    DEFAULT_MAX_IMAGES_PER_DAY,
    DEFAULT_POLLINATIONS_IMAGE_MODEL,
)




class AgentImageGenerationSetting(Base):
    __tablename__ = "agent_image_generation_settings"

    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"), primary_key=True
    )
    encrypted_openrouter_api_key: Mapped[str | None] = mapped_column(Text)
    encrypted_pollinations_api_key: Mapped[str | None] = mapped_column(Text)
    encrypted_replicate_api_token: Mapped[str | None] = mapped_column(Text)
    key_fingerprint: Mapped[str | None] = mapped_column(String(32))
    replicate_key_fingerprint: Mapped[str | None] = mapped_column(String(32))
    image_key_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="disabled"
    )
    image_generation_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    max_images_per_day: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_MAX_IMAGES_PER_DAY
    )
    openrouter_image_model: Mapped[str] = mapped_column(
        String(120), nullable=False, default="black-forest-labs/flux.2-klein-4b"
    )
    pollinations_image_model: Mapped[str] = mapped_column(
        String(80), nullable=False, default=DEFAULT_POLLINATIONS_IMAGE_MODEL
    )
    seed_image_url: Mapped[str | None] = mapped_column(String(500))
    visual_identity_prompt: Mapped[str | None] = mapped_column(Text)
    visual_identity_source_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    character: Mapped["Character"] = relationship(
        back_populates="image_generation_setting"
    )
