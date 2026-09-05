"""Same-Session aggregate reads used by Social discovery policies."""
from datetime import datetime
from typing import Protocol
from sqlalchemy.orm import Session
from app.domains.social.models.posts import Post


class TodayActivityRow(Protocol):
    id: str
    name: str
    handle: str
    avatar_url: str | None
    post_count: int | None
    reply_count: int | None
    like_count: int | None


class DiscoveryReads(Protocol):
    def search_posts(self, db: Session, query: str, *, limit: int, offset: int = 0) -> tuple[list[Post], int | None]: ...

    def list_today_activity_rows(self, db: Session, *, day_start: datetime, post_types: tuple[str, ...], reply_types: tuple[str, ...], like_types: tuple[str, ...]) -> list[TodayActivityRow]: ...
