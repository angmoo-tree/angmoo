"""Build one Social profile service with shared-Session foreign query collaborators."""

from sqlalchemy.orm import Session
from app.domains.social.service.world_profile import WorldSocialProfileService
from app.runtime.social.profile_references import RuntimeProfileReferences


def world_character_social_profile_service(db: Session) -> WorldSocialProfileService:
    return WorldSocialProfileService(db, references=RuntimeProfileReferences(db))
