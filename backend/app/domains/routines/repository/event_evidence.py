"""Nullable joint source lookup required by successful-event evidence."""
from sqlalchemy.orm import Session
from app.domains.routines import models


def get_joint_activity(db: Session, joint_activity_id: str) -> models.JointActivity | None:
    return db.get(models.JointActivity, joint_activity_id)
