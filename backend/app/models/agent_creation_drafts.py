from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class AgentCreationDraft(Base):
    __tablename__ = "agent_creation_drafts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="google")
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    key_fingerprint: Mapped[Optional[str]] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    handle: Mapped[Optional[str]] = mapped_column(String(40))
    one_liner: Mapped[str] = mapped_column(Text, nullable=False, default="")
    personality: Mapped[str] = mapped_column(Text, nullable=False, default="")
    speech_style: Mapped[str] = mapped_column(Text, nullable=False, default="")
    worldview: Mapped[str] = mapped_column(Text, nullable=False, default="")
    topic_preferences: Mapped[str] = mapped_column(Text, nullable=False, default="")
    safety_rules: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_style: Mapped[str] = mapped_column(String(40), nullable=False, default="기본")
    appearance_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    avatar_temp_url: Mapped[Optional[str]] = mapped_column(String(500))
    banner_temp_url: Mapped[Optional[str]] = mapped_column(String(500))
    persona_enhance_available_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    media_generation_available_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship()
