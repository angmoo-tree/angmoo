"""Canonical replay digest and visible root-post checks for source writes."""
from sqlalchemy.orm import Session
from app.domains.social.models import posts as models
from app.domains.social.models.manual_writes import OwnerManualSocialWrite
from app.domains.social.contracts.writes import SocialWriteConflictError, SocialWriteNotFoundError
from app.domains.social.repository import manual_writes as manual_queries


def _existing_write(
    db: Session,
    *,
    world_id: str,
    principal_user_id: str,
    idempotency_key: str,
    request_sha256: str,
) -> tuple[OwnerManualSocialWrite, models.Post] | None:
    row = manual_queries.find_ledger(db, world_id=world_id, principal_user_id=principal_user_id, idempotency_key=idempotency_key)
    if row is None:
        return None
    if row.request_sha256 != request_sha256:
        raise SocialWriteConflictError("idempotency_payload_mismatch")
    post = db.get(models.Post, row.result_post_id)
    if post is None or post.world_id != world_id:
        raise SocialWriteConflictError("idempotency_result_missing")
    return row, post


def _public_root_post(
    db: Session, *, world_id: str, target_post_id: str
) -> models.Post:
    post = db.get(models.Post, target_post_id)
    if (
        post is None
        or post.world_id != world_id
        or post.reply_to_post_id is not None
        or post.deleted_at is not None
        or post.report_hidden_at is not None
        or post.visibility != "public"
        or post.author_world_character_id is None
    ):
        raise SocialWriteNotFoundError("reply_target_unavailable")
    return post
