from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class TreePost(Base):
    __tablename__ = "tree_posts"
    __table_args__ = (
        CheckConstraint(
            "category in ('notice', 'bug', 'suggestion', 'question', 'free')",
            name="ck_tree_posts_category",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    related_character_id: Mapped[Optional[str]] = mapped_column(ForeignKey("characters.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    hidden_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    author: Mapped["User"] = relationship()
    related_character: Mapped[Optional["Character"]] = relationship()
    comments: Mapped[list["TreeComment"]] = relationship(
        back_populates="post", cascade="all, delete-orphan"
    )


class TreeComment(Base):
    __tablename__ = "tree_comments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    post_id: Mapped[str] = mapped_column(ForeignKey("tree_posts.id"), nullable=False)
    author_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    hidden_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    post: Mapped[TreePost] = relationship(back_populates="comments")
    author: Mapped["User"] = relationship()
