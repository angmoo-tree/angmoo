"""Public profile admission and safe activity response projection."""
from sqlalchemy.orm import Session
from app.domains.social.schemas import activity as schemas
from app.domains.social.contracts.activity import ActivityCharacter, ProfileActivityReads, PublicActivityLog
from app.domains.social.constants import PUBLIC_ACTIVITY_ACTION_ALIASES, PUBLIC_ACTIVITY_ACTION_TYPES, PUBLIC_ACTIVITY_SUMMARIES
from app.domains.social.exceptions import CharacterNotFoundError
from app.domains.social.repository.activity import recent_character_comments
from app.domains.characters.service import profile as character_profile


class ProfileActivityService:
    def __init__(self, reads: ProfileActivityReads):
        self.reads = reads

    def get_character_activity(
        self, db: Session, character_id: str
    ) -> schemas.CharacterActivityRead:
        character = character_profile.get_character(db, character_id)
        if character is None or character.deleted_at is not None:
            raise CharacterNotFoundError(character_id)

        return self.build_character_activity(db, character)

    def build_character_activity(
        self, db: Session, character: ActivityCharacter
    ) -> schemas.CharacterActivityRead:
        recent_comments = recent_character_comments(db, character_id=character.id)

        return schemas.CharacterActivityRead(
            character=schemas.PublicCharacterActivityProfileRead.model_validate(character),
            state=(
                schemas.PublicCharacterActivityStateRead.model_validate(character.state)
                if character.state
                else None
            ),
            recent_comments=[
                schemas.CommentRead.model_validate(comment) for comment in recent_comments
            ],
            recent_agent_activity=[
                _public_activity_event(log)
                for log in self.reads.recent_activity_logs(db, character_id=character.id)
            ],
        )


def _public_activity_event(
    log: PublicActivityLog,
) -> schemas.PublicCharacterActivityEventRead:
    action_type = PUBLIC_ACTIVITY_ACTION_ALIASES.get(log.action_type, log.action_type)
    if action_type not in PUBLIC_ACTIVITY_ACTION_TYPES:
        action_type = "activity_updated"
    return schemas.PublicCharacterActivityEventRead(
        id=log.id,
        action_type=action_type,
        target_post_id=log.target_post_id,
        summary=PUBLIC_ACTIVITY_SUMMARIES.get(
            action_type,
            "활동 기록이 업데이트됐어요.",
        ),
        created_at=log.created_at,
    )
