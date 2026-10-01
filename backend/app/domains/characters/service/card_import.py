"""Private card ownership and explicit replacement of a versioned creation draft."""
from sqlalchemy import select
from datetime import UTC, datetime

from app.core.ids import uuid7_string
from app.domains.characters import models
from app.domains.characters.service.card_mapping import map_card
from app.domains.characters.service.creator import _draft_read
from app.domains.characters.service.drafts import _get_owned_draft, claim_edit
from app.domains.characters.service.media_storage import save_draft_profile_media_bytes
from app.domains.characters.exceptions import AgentCreationDraftValidationError, AgentCreationDraftNotFoundError
from app.integrations.character_cards.parser import parse_card
from app.integrations.media.images import encode_profile_media_webp
from app.integrations.media.files import media_url_to_path


def _selection_summary(parsed):
    selection = parsed.metadata_selection
    if selection is None:
        return None
    return {"policy": selection.policy, "keyword": selection.keyword,
            "selected_occurrence": selection.selected_occurrence,
            "same_keyword_count": selection.same_keyword_count,
            "multiple_definitions": selection.multiple_definitions,
            "selected_json_sha256": selection.selected_json_sha256}


def import_card(db, user, draft_id, *, revision, content, workflows):
    draft = _get_owned_draft(db, user, draft_id, workflows=workflows)
    if draft.contract_version != 2:
        raise AgentCreationDraftValidationError("legacy_draft_card_import_unsupported")
    parsed = parse_card(content)
    mapping = map_card(parsed)
    claim_edit(db, draft, revision)
    created_file = None
    try:
        source = db.scalar(select(models.CharacterCardSource).where(models.CharacterCardSource.draft_id == draft.id))
        if source is None:
            source = models.CharacterCardSource(id=uuid7_string(), owner_id=user.id, draft_id=draft.id)
            db.add(source)
        source.source_bytes = content
        source.source_sha256 = parsed.source_sha256
        source.source_format = parsed.source_format
        source.card_version = parsed.version
        source.parser_version = parsed.parser_version
        for field, value in mapping.fields.items():
            setattr(draft, field, value)
        draft.source_kind = "card"
        draft.handle = None
        draft.avatar_temp_url = None
        draft.banner_temp_url = None
        if parsed.source_format == "png":
            display_image = encode_profile_media_webp(media_type="avatar", content=content)
            draft.avatar_temp_url = save_draft_profile_media_bytes(draft_id=draft.id,
                media_type="avatar", content_type="image/webp", content=display_image)
            created_file = media_url_to_path(draft.avatar_temp_url)
        db.commit()
    except Exception:
        db.rollback()
        if created_file is not None:
            created_file.unlink(missing_ok=True)
        raise
    return {"draft": _draft_read(draft), "card_version": parsed.version,
            "review": list(mapping.review), "raw_only": list(mapping.raw_only),
            "metadata_selection": _selection_summary(parsed)}


def read_source(db, user, draft_id, *, include_document=True):
    source = db.scalar(select(models.CharacterCardSource).where(
        models.CharacterCardSource.draft_id == draft_id, models.CharacterCardSource.owner_id == user.id))
    if source is None:
        raise AgentCreationDraftNotFoundError(draft_id)
    draft = db.get(models.AgentCreationDraft, draft_id)
    if source.character_id is None and (draft is None or draft.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC)):
        raise AgentCreationDraftNotFoundError(draft_id)
    parsed = parse_card(source.source_bytes)
    mapping = map_card(parsed)
    return {"document": parsed.document if include_document else None,
            "sha256": source.source_sha256, "version": source.card_version,
            "source_format": source.source_format,
            "metadata_selection": _selection_summary(parsed),
            "review": list(mapping.review), "raw_only": list(mapping.raw_only)}
