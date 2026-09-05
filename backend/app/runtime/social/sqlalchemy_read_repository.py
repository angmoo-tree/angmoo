"""Same-Session composition for the owner's canonical World feed/thread reads."""
from sqlalchemy.orm import Session
from app.domains.social.schemas.manual import ManualSocialFeedRead
from app.domains.social.contracts.writes import SocialWriteConflictError as ManualSocialConflictError, SocialWriteError as ManualSocialError, SocialWriteForbiddenError as ManualSocialForbiddenError, SocialWriteNotFoundError as ManualSocialNotFoundError
from app.domains.social.service import manual_feed
from app.runtime.social.manual_feed_references import RuntimeManualFeedReferences


def list_owner_world_feed(db: Session, *, world_id: str, current_user_id: str, limit: int = 100) -> ManualSocialFeedRead:
    return manual_feed.list_owner_world_feed(db, references=RuntimeManualFeedReferences(db), world_id=world_id, current_user_id=current_user_id, limit=limit)


def get_owner_world_post_thread(db: Session, *, world_id: str, post_id: str, current_user_id: str) -> ManualSocialFeedRead:
    return manual_feed.get_owner_world_post_thread(db, references=RuntimeManualFeedReferences(db), world_id=world_id, post_id=post_id, current_user_id=current_user_id)


__all__ = [
    "ManualSocialConflictError", "ManualSocialError", "ManualSocialForbiddenError", "ManualSocialNotFoundError",
    "get_owner_world_post_thread", "list_owner_world_feed",
]
