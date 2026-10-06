"""Installation owner environment and durable timezone transition history."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class LocalEnvironment(Base):
    __tablename__ = "local_environments"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    installation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    preferred_language: Mapped[str | None] = mapped_column(String(80), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    environment_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    timezone_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_client_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_session_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class EnvironmentTimezoneChange(Base):
    __tablename__ = "environment_timezone_changes"
    __table_args__ = (UniqueConstraint("owner_id", "revision", name="uq_environment_zone_revision"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_timezone: Mapped[str] = mapped_column(String(80), nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
