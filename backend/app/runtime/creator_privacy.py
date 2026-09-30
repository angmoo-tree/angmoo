"""Remove new creator-private records inside the existing deletion transaction."""
from sqlalchemy import delete, select
from app.domains.characters.models import (
    AgentCreationDraft, CharacterCardSource, CharacterRegistrationReceipt, ProfileImageCandidate,
)
from app.domains.world_characters.models import CharacterWorldBinding
from app.domains.worlds.models import OwnerDefaultWorld


def delete_creator_private_data(db, *, character_ids, owner_id=None):
    from app.runtime.media.privacy import scrub
    scrub(db, character_ids=character_ids, owner_id=owner_id)
    draft_ids = list(db.scalars(select(CharacterRegistrationReceipt.draft_id).where(
        CharacterRegistrationReceipt.character_id.in_(character_ids))))
    source_condition = (CharacterCardSource.owner_id == owner_id if owner_id is not None
                        else CharacterCardSource.character_id.in_(character_ids))
    db.execute(delete(CharacterCardSource).where(source_condition))
    db.execute(delete(CharacterRegistrationReceipt).where(
        CharacterRegistrationReceipt.character_id.in_(character_ids)))
    db.execute(delete(CharacterWorldBinding).where(CharacterWorldBinding.character_id.in_(character_ids)))
    if draft_ids:
        # Completed draft media have been promoted; discard its private source
        # fields with the receipt. Old candidate rows may still reference it.
        db.execute(delete(ProfileImageCandidate).where(ProfileImageCandidate.draft_id.in_(draft_ids)))
        db.execute(delete(AgentCreationDraft).where(AgentCreationDraft.id.in_(draft_ids)))
    if owner_id is not None:
        db.execute(delete(OwnerDefaultWorld).where(OwnerDefaultWorld.owner_id == owner_id))
