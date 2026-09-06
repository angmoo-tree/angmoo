"""Nullable joint source lookup required by successful-event evidence."""
from sqlalchemy.orm import Session
from app.domains.routines import models


def get_joint_activity(db: Session, joint_activity_id: str) -> models.JointActivity | None:
    return db.get(models.JointActivity, joint_activity_id)


from sqlalchemy import select


def find_joint_for_proposal(db: Session, *, proposal_id: str) -> models.JointActivity | None:
    return db.scalar(
            select(models.JointActivity).where(
                models.JointActivity.proposal_id == proposal_id
            )
        )
