"""Character promotion agreement timestamps; the caller owns persistence."""
from datetime import UTC, datetime
from app.domains.characters import models, schemas


PROMOTION_USAGE_POLICY_VERSION = "2026-06-25"

def _set_promotion_usage(character: models.Character, allowed: bool) -> None:
    now = datetime.now(UTC)
    was_allowed = bool(character.promotion_usage_allowed)
    character.promotion_usage_allowed = allowed
    if allowed:
        if not was_allowed:
            character.promotion_usage_agreed_at = now
        character.promotion_usage_revoked_at = None
        character.promotion_usage_policy_version = PROMOTION_USAGE_POLICY_VERSION
        return
    if was_allowed:
        character.promotion_usage_revoked_at = now

def _promotion_usage_read(character: models.Character) -> schemas.AgentPromotionUsageRead:
    return schemas.AgentPromotionUsageRead(
        promotion_usage_allowed=bool(character.promotion_usage_allowed),
        promotion_usage_agreed_at=character.promotion_usage_agreed_at,
        promotion_usage_revoked_at=character.promotion_usage_revoked_at,
        promotion_usage_policy_version=character.promotion_usage_policy_version,
    )
