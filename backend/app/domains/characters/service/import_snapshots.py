"""Capture only on final creation/migration; reads and copies never recapture."""
from app.domains.characters.models_import import CharacterImportOrigin, CharacterImportSnapshot, CharacterDraftImportOrigin
from app.domains.characters.contracts import ImportConfiguration, import_digest
from sqlalchemy import select


def get_import_snapshot(db, character_id):
    origin = db.get(CharacterImportOrigin, character_id)
    if origin is None:
        raise ValueError("character_import_origin_missing")
    row = db.get(CharacterImportSnapshot, origin.snapshot_id)
    if row is None or row.digest != import_digest(row.payload):
        raise ValueError("character_import_origin_invalid")
    return row, ImportConfiguration.model_validate(row.payload)


def capture_creation(db, *, character_id, configuration: ImportConfiguration, provenance: str):
    if db.get(CharacterImportOrigin, character_id) is not None:
        return get_import_snapshot(db, character_id)[0]
    payload = configuration.model_dump(mode="json")
    row = CharacterImportSnapshot(source_character_id=character_id, kind="creation", contract_version=1,
        source_revision="creation:1", provenance=provenance, payload=payload, digest=import_digest(payload))
    db.add(row)
    db.flush()
    db.add(CharacterImportOrigin(character_id=character_id, snapshot_id=row.id))
    db.flush()
    return row


def attach_copy_origin(db, *, draft_id, character_id):
    link = db.get(CharacterDraftImportOrigin, draft_id)
    if link is None:
        return None
    db.add(CharacterImportOrigin(character_id=character_id, snapshot_id=link.snapshot_id))
    db.flush()
    return db.get(CharacterImportSnapshot, link.snapshot_id)


def retained_import_media_urls(db, *, excluding_character_id):
    """Keep origin files while a surviving identity or copy draft uses the basis."""
    from app.domains.characters.models import Character, AgentCreationDraft
    surviving = select(CharacterImportOrigin.snapshot_id).join(Character,
        Character.id == CharacterImportOrigin.character_id).where(Character.deleted_at.is_(None),
        Character.id != excluding_character_id)
    preparing = select(CharacterDraftImportOrigin.snapshot_id).join(AgentCreationDraft,
        AgentCreationDraft.id == CharacterDraftImportOrigin.draft_id).where(AgentCreationDraft.status.in_(("editing", "registering")))
    rows = db.scalars(select(CharacterImportSnapshot).where(
        CharacterImportSnapshot.id.in_(surviving.union(preparing))))
    result = set()
    for row in rows:
        if row.digest != import_digest(row.payload):
            raise ValueError("character_import_origin_invalid")
        profile = ImportConfiguration.model_validate(row.payload).profile
        result.update(url for url in (profile.avatar_url, profile.banner_url) if url)
    return result
