"""Remove new creator-private records inside the existing deletion transaction."""
from sqlalchemy import delete, exists, or_, select
from app.domains.characters.models import (
    AgentCreationDraft, CharacterCardSource, CharacterRegistrationReceipt, ProfileImageCandidate,
)
from app.domains.characters.models_import import CharacterDraftImportOrigin, CharacterImportOrigin, CharacterImportSnapshot
from app.domains.world_characters.models import CharacterWorldBinding, WorldCharacter
from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
from app.domains.worlds.models import OwnerDefaultWorld


def delete_creator_private_data(db, *, character_ids, owner_id=None):
    from app.runtime.media.privacy import scrub
    scrub(db, character_ids=character_ids, owner_id=owner_id)
    draft_ids = list(db.scalars(select(CharacterRegistrationReceipt.draft_id).where(
        CharacterRegistrationReceipt.character_id.in_(character_ids))))
    private_draft_ids = set(draft_ids)
    if owner_id is not None:
        private_draft_ids.update(db.scalars(select(AgentCreationDraft.id).where(AgentCreationDraft.user_id == owner_id)))
    _delete_import_configuration_data(db, character_ids=character_ids, draft_ids=private_draft_ids)
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


def _delete_import_configuration_data(db, *, character_ids, draft_ids):
    """Erase private links in this UoW; preserve a basis used by another instance.

    Ordinary edits cannot change snapshots. Privacy erasure uses an explicit
    bulk delete only after every origin, draft and World reference is absent.
    It never changes the payload of a retained, shared immutable snapshot.
    """
    candidates = set(db.scalars(select(CharacterImportSnapshot.id).where(
        CharacterImportSnapshot.source_character_id.in_(character_ids))))
    candidates.update(db.scalars(select(CharacterImportOrigin.snapshot_id).where(
        CharacterImportOrigin.character_id.in_(character_ids))))
    candidates.update(db.scalars(select(CharacterDraftImportOrigin.snapshot_id).where(
        CharacterDraftImportOrigin.draft_id.in_(draft_ids))))
    role_ids = select(WorldCharacter.id).where(WorldCharacter.character_id.in_(character_ids))
    db.execute(delete(WorldCharacterConfiguration).where(WorldCharacterConfiguration.world_character_id.in_(role_ids)))
    db.execute(delete(CharacterDraftImportOrigin).where(CharacterDraftImportOrigin.draft_id.in_(draft_ids)))
    db.execute(delete(CharacterImportOrigin).where(CharacterImportOrigin.character_id.in_(character_ids)))
    referenced = or_(
        exists(select(1).where(CharacterImportOrigin.snapshot_id == CharacterImportSnapshot.id)),
        exists(select(1).where(CharacterDraftImportOrigin.snapshot_id == CharacterImportSnapshot.id)),
        exists(select(1).where(WorldCharacterConfiguration.snapshot_id == CharacterImportSnapshot.id)),
    )
    db.execute(delete(CharacterImportSnapshot).where(CharacterImportSnapshot.id.in_(candidates), ~referenced))
