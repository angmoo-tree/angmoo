"""Connect Today policy and the existing caller Session without eager IO."""

from sqlalchemy.orm import Session
from app.domains.social.service.today_activity import TodaySocialActivityService
from app.runtime.social.today_activity_queries import RuntimeTodayReferences


def today_social_activity_reader(db: Session) -> TodaySocialActivityService:
    from app.config import settings
    return TodaySocialActivityService(db, references=RuntimeTodayReferences(db),
        thought_enabled=settings.ACTIVITY_THOUGHT_POLICY == "thought_v1")
