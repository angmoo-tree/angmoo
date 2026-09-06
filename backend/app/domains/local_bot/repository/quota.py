from datetime import datetime
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.domains.local_bot import models

def _ensure_action_bucket(
    db: Session,
    *,
    character_id: str,
    action_label: str,
) -> None:
    if db.get(
        models.LocalBotActionQuotaBucket,
        {
            "character_id": character_id,
            "action_label": action_label,
        },
    ) is not None:
        return
    try:
        with db.begin_nested():
            db.add(
                models.LocalBotActionQuotaBucket(
                    character_id=character_id,
                    action_label=action_label,
                    used_count=0,
                )
            )
            db.flush()
    except IntegrityError:
        pass

def _ensure_read_bucket(
    db: Session,
    *,
    local_key_id: str,
    now: datetime,
) -> None:
    if db.get(models.LocalBotReadQuotaBucket, local_key_id) is not None:
        return
    try:
        with db.begin_nested():
            db.add(
                models.LocalBotReadQuotaBucket(
                    local_key_id=local_key_id,
                    window_started_at=now,
                    used_count=0,
                )
            )
            db.flush()
    except IntegrityError:
        pass

def read_read_bucket(db: Session, local_key_id):
    return db.scalar(
        select(models.LocalBotReadQuotaBucket)
        .where(models.LocalBotReadQuotaBucket.local_key_id == local_key_id)
        .with_for_update()
    )


def read_action_buckets(db: Session, character_id, ordered_labels):
    return db.scalars(
            select(models.LocalBotActionQuotaBucket)
            .where(
                models.LocalBotActionQuotaBucket.character_id == character_id,
                models.LocalBotActionQuotaBucket.action_label.in_(ordered_labels),
            )
            .order_by(models.LocalBotActionQuotaBucket.action_label.asc())
            .with_for_update()
        )
