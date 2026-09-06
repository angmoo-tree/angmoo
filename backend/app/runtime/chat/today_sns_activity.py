"""Construct Chat snapshot validation with its same-Session Today reader."""

from sqlalchemy.orm import Session
from app.domains.chat.service.today_sns_activity import TodaySnsSnapshotValidator
from app.runtime.social.today_activity import today_social_activity_reader as SqlAlchemyTodaySocialActivityReader


def build_today_snapshot_validator(
    db: Session, character_labels: dict[str, str]
) -> TodaySnsSnapshotValidator:
    return TodaySnsSnapshotValidator(
        SqlAlchemyTodaySocialActivityReader(db), character_labels
    )


SqlAlchemyTodaySnsSnapshotValidator = build_today_snapshot_validator
