"""Character text search with the original public listing and pagination rules."""
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from app.core.search_text import _like_search_terms, _like_pattern
from app.domains.characters import models


def search_characters(
    db: Session, query: str, *, limit: int, offset: int = 0
) -> tuple[list[models.Character], int | None]:
    filters = []
    for term in _like_search_terms(query):
        pattern = _like_pattern(term)
        filters.extend(
            [
                models.Character.name.ilike(pattern, escape="\\"),
                models.Character.handle.ilike(pattern, escape="\\"),
                models.Character.one_liner.ilike(pattern, escape="\\"),
                models.Character.persona_summary.ilike(pattern, escape="\\"),
            ]
        )
    if not filters:
        return [], None
    rows = list(
        db.scalars(
            select(models.Character)
            .where(models.Character.deleted_at.is_(None), or_(*filters))
            .order_by(models.Character.created_at.desc(), models.Character.id.asc())
            .offset(max(0, offset))
            .limit(limit + 1)
        )
    )
    return rows[:limit], offset + limit if len(rows) > limit else None
