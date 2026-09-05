"""Manual/autonomous write ledger and inbox delivery lookup, without commits."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.social.models.manual_writes import OwnerManualSocialWrite, OwnerManualInboxCandidate


def find_ledger(db: Session, *, world_id: str, principal_user_id: str, idempotency_key: str) -> OwnerManualSocialWrite | None:
    return db.scalar(
        select(OwnerManualSocialWrite).where(
            OwnerManualSocialWrite.world_id == world_id,
            OwnerManualSocialWrite.owner_user_id == principal_user_id,
            OwnerManualSocialWrite.idempotency_key == idempotency_key,
        )
    )


def _candidate(
    db: Session, *, reply_id: str, target_id: str
) -> OwnerManualInboxCandidate | None:
    return db.scalar(
        select(OwnerManualInboxCandidate).where(
            OwnerManualInboxCandidate.source_reply_post_id == reply_id,
            OwnerManualInboxCandidate.target_world_character_id == target_id,
        )
    )
