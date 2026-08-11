from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        CheckConstraint(
            "info_kind is null or info_kind in "
            "('weather', 'news', 'calendar', 'market', 'knowledge', 'other')",
            name="ck_posts_info_kind",
        ),
        CheckConstraint(
            "(world_id IS NULL AND author_world_character_id IS NULL) OR "
            "(world_id IS NOT NULL AND author_world_character_id IS NOT NULL)",
            name="ck_posts_world_scope_pair",
        ),
        ForeignKeyConstraint(
            ["author_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_posts_author_world_character_scope",
        ),
        ForeignKeyConstraint(
            ["author_world_character_id", "author_character_id"],
            ["world_characters.id", "world_characters.character_id"],
            name="fk_posts_author_world_character_identity",
        ),
        UniqueConstraint("id", "world_id", name="uq_posts_id_world"),
        Index("ix_posts_world_created_at", "world_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    author_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    author_character_id: Mapped[Optional[str]] = mapped_column(ForeignKey("characters.id"))
    world_id: Mapped[Optional[str]] = mapped_column(ForeignKey("worlds.id"))
    author_world_character_id: Mapped[Optional[str]] = mapped_column(String(64))
    reply_to_post_id: Mapped[Optional[str]] = mapped_column(ForeignKey("posts.id"))
    quote_post_id: Mapped[Optional[str]] = mapped_column(ForeignKey("posts.id"))
    repost_of_post_id: Mapped[Optional[str]] = mapped_column(ForeignKey("posts.id"))
    post_type: Mapped[str] = mapped_column(String(20), default="post", nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), default="public", nullable=False)
    author_name: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    topic_signature: Mapped[Optional[str]] = mapped_column(Text)
    search_document: Mapped[str] = mapped_column(Text, nullable=False, default="")
    novelty_basis: Mapped[Optional[str]] = mapped_column(Text)
    info_kind: Mapped[Optional[str]] = mapped_column(String(40))
    source_name: Mapped[Optional[str]] = mapped_column(String(120))
    source_url: Mapped[Optional[str]] = mapped_column(String(500))
    observed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    location_label: Mapped[Optional[str]] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    report_count: Mapped[int] = mapped_column(default=0, nullable=False)
    report_hidden_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    comments: Mapped[list["Comment"]] = relationship(
        back_populates="post", cascade="all, delete-orphan"
    )
    likes: Mapped[list["PostLike"]] = relationship(
        back_populates="post", cascade="all, delete-orphan"
    )
    repost_events: Mapped[list["PostRepost"]] = relationship(
        back_populates="post", cascade="all, delete-orphan"
    )
    media: Mapped[list["PostMedia"]] = relationship(
        back_populates="post", cascade="all, delete-orphan"
    )


class PostMedia(Base):
    __tablename__ = "post_media"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    post_id: Mapped[str] = mapped_column(ForeignKey("posts.id"), nullable=False, index=True)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False, default="image")
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    alt_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    key_source: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    post: Mapped[Post] = relationship(back_populates="media")


class PostImageGenerationJob(Base):
    __tablename__ = "post_image_generation_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    post_id: Mapped[str] = mapped_column(
        ForeignKey("posts.id"), nullable=False, unique=True, index=True
    )
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="local_api")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    key_source: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    quota_reservation_id: Mapped[int | None] = mapped_column(
        ForeignKey("post_image_quota_reservations.id")
    )
    image_model: Mapped[str] = mapped_column(String(120), nullable=False)
    image_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_hash: Mapped[str | None] = mapped_column(String(64))
    reference_source: Mapped[str | None] = mapped_column(String(40))
    skip_reason: Mapped[str | None] = mapped_column(String(80))
    failure_class: Mapped[str | None] = mapped_column(String(120))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    media_url: Mapped[str | None] = mapped_column(String(500))
    byte_size: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    post: Mapped[Post] = relationship()
    character: Mapped["Character"] = relationship()
    quota_reservation: Mapped[Optional["PostImageQuotaReservation"]] = relationship(
        back_populates="job"
    )


class PostImageQuotaReservation(Base):
    __tablename__ = "post_image_quota_reservations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"), nullable=False, index=True
    )
    quota_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    key_source: Mapped[str] = mapped_column(String(20), nullable=False, default="service")
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="reserved")
    post_id: Mapped[str | None] = mapped_column(ForeignKey("posts.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job: Mapped[Optional[PostImageGenerationJob]] = relationship(
        back_populates="quota_reservation",
        primaryjoin="PostImageQuotaReservation.id==PostImageGenerationJob.quota_reservation_id",
    )


class PostLike(Base):
    __tablename__ = "post_likes"
    __table_args__ = (
        UniqueConstraint("post_id", "character_id", name="uq_post_likes_post_character"),
        Index(
            "uq_post_likes_post_user_direct",
            "post_id",
            "user_id",
            unique=True,
            postgresql_where=text("character_id IS NULL"),
            sqlite_where=text("character_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    post_id: Mapped[str] = mapped_column(ForeignKey("posts.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    character_id: Mapped[Optional[str]] = mapped_column(ForeignKey("characters.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    post: Mapped[Post] = relationship(back_populates="likes")
    character: Mapped["Character"] = relationship()


class PostRepost(Base):
    __tablename__ = "post_reposts"
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_post_reposts_post_user"),
        UniqueConstraint("post_id", "character_id", name="uq_post_reposts_post_character"),
        CheckConstraint(
            "(user_id is null) <> (character_id is null)",
            name="ck_post_reposts_actor_exactly_one",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    post_id: Mapped[str] = mapped_column(ForeignKey("posts.id"), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    character_id: Mapped[Optional[str]] = mapped_column(ForeignKey("characters.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    post: Mapped[Post] = relationship(back_populates="repost_events")
    character: Mapped[Optional["Character"]] = relationship()


class PostReport(Base):
    __tablename__ = "post_reports"
    __table_args__ = (
        UniqueConstraint("post_id", "reporter_user_id", name="uq_post_reports_post_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    post_id: Mapped[str] = mapped_column(ForeignKey("posts.id"), nullable=False)
    reporter_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    post_id: Mapped[str] = mapped_column(ForeignKey("posts.id"), nullable=False)
    author_character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    post: Mapped[Post] = relationship(back_populates="comments")
    author_character: Mapped["Character"] = relationship(back_populates="comments")


class ProfileFollow(Base):
    __tablename__ = "profile_follows"
    __table_args__ = (
        UniqueConstraint(
            "follower_user_id", "target_user_id", name="uq_profile_follows_user_user"
        ),
        UniqueConstraint(
            "follower_user_id",
            "target_character_id",
            name="uq_profile_follows_user_character",
        ),
        UniqueConstraint(
            "follower_character_id",
            "target_user_id",
            name="uq_profile_follows_character_user",
        ),
        UniqueConstraint(
            "follower_character_id",
            "target_character_id",
            name="uq_profile_follows_character_character",
        ),
        CheckConstraint(
            "(follower_user_id is null) <> (follower_character_id is null)",
            name="ck_profile_follows_follower_exactly_one",
        ),
        CheckConstraint(
            "(target_user_id is null) <> (target_character_id is null)",
            name="ck_profile_follows_target_exactly_one",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    follower_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    follower_character_id: Mapped[Optional[str]] = mapped_column(ForeignKey("characters.id"))
    target_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    target_character_id: Mapped[Optional[str]] = mapped_column(ForeignKey("characters.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "(recipient_user_id is null) <> (recipient_character_id is null)",
            name="ck_notifications_recipient_exactly_one",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipient_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    recipient_character_id: Mapped[Optional[str]] = mapped_column(ForeignKey("characters.id"))
    actor_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    actor_character_id: Mapped[Optional[str]] = mapped_column(ForeignKey("characters.id"))
    notification_type: Mapped[str] = mapped_column(String(40), nullable=False)
    post_id: Mapped[Optional[str]] = mapped_column(ForeignKey("posts.id"))
    source_post_id: Mapped[Optional[str]] = mapped_column(ForeignKey("posts.id"))
    data: Mapped[Optional[str]] = mapped_column(Text)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
