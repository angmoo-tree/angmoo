from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


DISPLAY_NAME_CHANGE_COOLDOWN = timedelta(days=1)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    google_sub: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    is_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    display_name_normalized: Mapped[Optional[str]] = mapped_column(
        String(80), unique=True, nullable=True
    )
    display_name_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    privacy_policy_agreed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    terms_agreed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    privacy_policy_version: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    terms_version: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    profile_setup_completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    feed_content_filter: Mapped[str] = mapped_column(
        String(20), nullable=False, default="all", server_default="all"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    characters: Mapped[list["Character"]] = relationship(
        back_populates="owner", foreign_keys="Character.owner_id"
    )

    @property
    def display_name_change_available_at(self) -> Optional[datetime]:
        if not self.profile_setup_completed or self.display_name_updated_at is None:
            return None
        updated_at = self.display_name_updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        return updated_at + DISPLAY_NAME_CHANGE_COOLDOWN


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    auth_method: Mapped[str] = mapped_column(String(20), nullable=False, default="password")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship()


class AuthLoginThrottleBucket(Base):
    __tablename__ = "auth_login_throttle_buckets"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('source','account_source')",
            name="ck_auth_login_throttle_scope",
        ),
        CheckConstraint(
            "failure_count >= 0",
            name="ck_auth_login_throttle_failure_nonnegative",
        ),
    )

    scope: Mapped[str] = mapped_column(String(24), primary_key=True)
    subject_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    failure_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    blocked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_failure_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AuthExternalVerificationReservation(Base):
    __tablename__ = "auth_external_verification_reservations"
    __table_args__ = (
        CheckConstraint(
            "provider IN ('google')",
            name="ck_auth_external_verification_provider",
        ),
        CheckConstraint(
            "outcome_class IS NULL OR "
            "outcome_class IN ('success','invalid','error')",
            name="ck_auth_external_verification_outcome",
        ),
        Index(
            "ix_auth_external_verification_provider_source_created",
            "provider",
            "source_hash",
            "created_at",
        ),
        Index(
            "ix_auth_external_verification_provider_lease",
            "provider",
            "lease_expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    outcome_class: Mapped[str | None] = mapped_column(String(20), nullable=True)


class AuthGoogleSignupGrant(Base):
    __tablename__ = "auth_google_signup_grants"

    jti_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CommunityMutationQuotaBucket(Base):
    __tablename__ = "community_mutation_quota_buckets"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('reply_minute','reply_day','report_10m','report_day')",
            name="ck_community_mutation_quota_scope",
        ),
        CheckConstraint(
            "used_count >= 0",
            name="ck_community_mutation_quota_used_nonnegative",
        ),
    )

    scope: Mapped[str] = mapped_column(String(24), primary_key=True)
    subject_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
