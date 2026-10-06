"""Compose existing account/Character scrubbing with canonical Memory cleanup."""

from sqlalchemy import delete, or_, select

from app.models import Base
from app.domains.memory.models.items import MemoryCandidate
from app.domains.memory.models.items import MemoryHotBrief
from app.domains.memory.models.items import MemoryHotBriefItem
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.models.items import MemoryItemEvidence
from app.domains.memory.models.items import MemoryMaintenanceJob
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.memory.models.batch import MemoryBatchProfile
from app.domains.memory.models.activity_configuration import MemoryEpisodeRestriction, MemoryIndexPreparation, MemorySubjectProfile


def scrub_memory_data(session, *, owner_id: str, character_id: str | None = None):
    from app.domains.identity.models_world_credentials import WorldCredential, WorldCredentialRevision
    from app.domains.media.models_world_policy import WorldImagePolicy, WorldImageAttempt
    from app.domains.characters.models import Character
    from app.domains.world_characters.models import WorldCharacter
    subjects = select(WorldCharacter.id).join(Character, Character.id == WorldCharacter.character_id).where(Character.owner_id == owner_id)
    if character_id is not None:
        subjects = subjects.where(Character.id == character_id)
    credentials = select(WorldCredential.id).where(WorldCredential.owner_id == owner_id, WorldCredential.world_character_id.in_(subjects))
    session.execute(delete(WorldCredentialRevision).where(WorldCredentialRevision.credential_id.in_(credentials)))
    session.execute(delete(WorldCredential).where(WorldCredential.id.in_(credentials)))
    session.execute(delete(WorldImageAttempt).where(WorldImageAttempt.world_character_id.in_(subjects)))
    session.execute(delete(WorldImagePolicy).where(WorldImagePolicy.world_character_id.in_(subjects)))
    scopes = select(MemoryScopeSettingModel.id).where(
        MemoryScopeSettingModel.owner_id == owner_id
    )
    owned_items = MemoryItem.owner_id == owner_id
    if character_id is not None:
        characters = Base.metadata.tables["world_characters"]
        subjects = select(characters.c.id).where(
            characters.c.character_id == character_id
        )
        scopes = scopes.where(
            MemoryScopeSettingModel.subject_world_character_id.in_(subjects)
        )
        threads = Base.metadata.tables["message_threads"]
        removed_threads = select(threads.c.id).where(
            threads.c.character_id == character_id
        )
        owned_items = owned_items & or_(
            MemoryItem.subject_world_character_id.in_(subjects),
            MemoryItem.thread_id.in_(removed_threads),
        )
    item_ids = select(MemoryItem.id).where(owned_items)
    brief_ids = select(MemoryHotBrief.id).where(
        MemoryHotBrief.scope_setting_id.in_(scopes)
    )
    # Legacy Memory foreign keys do not cascade. New v2 tables cascade from
    # their scope/job/candidate roots; the installation model survives a single
    # Character deletion. All changes share the caller's scrub transaction.
    session.execute(
        delete(MemoryHotBriefItem).where(
            or_(
                MemoryHotBriefItem.brief_id.in_(brief_ids),
                MemoryHotBriefItem.memory_item_id.in_(item_ids),
            )
        )
    )
    session.execute(delete(MemoryHotBrief).where(MemoryHotBrief.id.in_(brief_ids)))
    session.execute(delete(MemoryEpisodeRestriction).where(MemoryEpisodeRestriction.memory_item_id.in_(item_ids)))
    session.execute(delete(MemoryIndexPreparation).where(MemoryIndexPreparation.scope_setting_id.in_(scopes)))
    session.execute(delete(MemorySubjectProfile).where(MemorySubjectProfile.scope_setting_id.in_(scopes)))
    session.execute(
        delete(MemoryItemEvidence).where(
            MemoryItemEvidence.memory_item_id.in_(item_ids)
        )
    )
    session.execute(
        delete(MemoryMaintenanceJob).where(
            MemoryMaintenanceJob.scope_setting_id.in_(scopes)
        )
    )
    session.execute(
        delete(MemoryCandidate).where(MemoryCandidate.scope_setting_id.in_(scopes))
    )
    session.execute(delete(MemoryItem).where(owned_items))
    session.execute(
        delete(MemoryScopeSettingModel).where(MemoryScopeSettingModel.id.in_(scopes))
    )
    if character_id is None:
        session.execute(
            delete(MemoryBatchProfile).where(MemoryBatchProfile.owner_id == owner_id)
        )
