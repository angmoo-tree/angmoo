"""Cross-owner search and activity aggregates preserve their original SQL shape."""
from datetime import datetime
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session
from app.core.search_text import _like_search_terms, _like_pattern
from app.domains.characters.models import Character
from app.domains.social.models.posts import Post
from app.domains.social.contracts.discovery import TodayActivityRow
from app.domains.social.repository.posts import _visible_post_conditions, _visible_reference_conditions
from app.models.agent_runs import AgentActivityLog
from app.cruds import agents as agent_crud
from app.domains.social.service.discovery import SocialDiscoveryService


class SqlAlchemyDiscoveryReads:
    def search_posts(
        self, db: Session, query: str, *, limit: int, offset: int = 0
    ) -> tuple[list[Post], int | None]:
        filters = []
        for term in _like_search_terms(query):
            pattern = _like_pattern(term)
            filters.extend(
                [
                    Post.title.ilike(pattern, escape="\\"),
                    Post.body.ilike(pattern, escape="\\"),
                    Post.author_name.ilike(pattern, escape="\\"),
                    Character.name.ilike(pattern, escape="\\"),
                    Character.handle.ilike(pattern, escape="\\"),
                ]
            )
        if not filters:
            return [], None
        rows = list(
            db.scalars(
                select(Post)
                .outerjoin(
                    Character,
                    Post.author_character_id == Character.id,
                )
                .where(
                    *_visible_post_conditions(),
                    *_visible_reference_conditions(),
                    Post.visibility == "public",
                    or_(*filters),
                )
                .order_by(Post.created_at.desc(), Post.id.asc())
                .offset(max(0, offset))
                .limit(limit + 1)
            )
        )
        return rows[:limit], offset + limit if len(rows) > limit else None

    def list_today_activity_rows(self, db: Session, *, day_start: datetime, post_types: tuple[str, ...], reply_types: tuple[str, ...], like_types: tuple[str, ...]) -> list[TodayActivityRow]:
        return db.execute(
                select(
                    Character.id,
                    Character.name,
                    Character.handle,
                    Character.avatar_url,
                    func.sum(
                        case((AgentActivityLog.action_type.in_(post_types), 1), else_=0)
                    ).label("post_count"),
                    func.sum(
                        case((AgentActivityLog.action_type.in_(reply_types), 1), else_=0)
                    ).label("reply_count"),
                    func.sum(
                        case((AgentActivityLog.action_type.in_(like_types), 1), else_=0)
                    ).label("like_count"),
                )
                .join(
                    AgentActivityLog,
                    AgentActivityLog.character_id == Character.id,
                )
                .where(AgentActivityLog.created_at >= day_start)
                .where(
                    AgentActivityLog.action_type.not_in(
                        agent_crud.HIDDEN_ACTIVITY_ACTION_TYPES
                    )
                )
                .group_by(
                    Character.id,
                    Character.name,
                    Character.handle,
                    Character.avatar_url,
                )
            ).all()


discovery_reads = SqlAlchemyDiscoveryReads()
discovery_service = SocialDiscoveryService(discovery_reads)
