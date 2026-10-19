"""Private card ownership and explicit replacement of a versioned creation draft."""
from sqlalchemy import select
from dataclasses import dataclass
from app.core.sqlite_concurrency import require_read_only_session, run_sqlite_session_immediate
from app.integrations.media.card_staging import PreparedDisplay, prepare_display
from datetime import UTC, datetime

from app.core.ids import uuid7_string
from app.domains.characters import models
from app.domains.characters.service.card_mapping import CardMapping, map_card
from app.domains.characters.service.creator import _draft_read
from app.domains.characters.service.drafts import _get_owned_draft, claim_edit
from app.domains.characters.exceptions import AgentCreationDraftValidationError, AgentCreationDraftNotFoundError
from app.integrations.character_cards.parser import ParsedCard, parse_card
from app.integrations.media.images import encode_profile_media_webp, validate_profile_media_content

from app.domains.characters.service.card_cleanup import display_is_referenced


def _selection_summary(parsed):
    selection = parsed.metadata_selection
    if selection is None:
        return None
    return {"policy": selection.policy, "keyword": selection.keyword,
            "selected_occurrence": selection.selected_occurrence,
            "same_keyword_count": selection.same_keyword_count,
            "multiple_definitions": selection.multiple_definitions,
            "selected_json_sha256": selection.selected_json_sha256}


@dataclass(frozen=True)
class ImportOwner:
    id: str


@dataclass(frozen=True)
class PreparedCard:
    parsed: ParsedCard
    mapping: CardMapping
    display: PreparedDisplay | None



def import_card(db, user, draft_id, *, revision, content, workflows):
    """Own the request UoW: authorize/read, prepare without SQLite, fresh apply."""
    require_read_only_session(db, error_code="card_import_requires_clean_unit_of_work")
    draft = _get_owned_draft(db, user, draft_id, workflows=workflows)
    if draft.contract_version != 2:
        raise AgentCreationDraftValidationError("legacy_draft_card_import_unsupported")
    if draft.status != "editing" or draft.revision != revision:
        from app.domains.characters.exceptions import AgentCreationDraftHandleConflictError
        raise AgentCreationDraftHandleConflictError("draft_revision_conflict")
    user = ImportOwner(user.id)
    db.rollback()
    parsed = parse_card(content)
    mapping = map_card(parsed)
    display = None
    if parsed.source_format == "png":
        encoded = encode_profile_media_webp(media_type="avatar", content=content)
        validate_profile_media_content("image/webp", encoded)
        display = prepare_display(draft_id=draft_id, encoded=encoded)
    prepared = PreparedCard(parsed, mapping, display)
    def apply():
        fresh = _get_owned_draft(db, user, draft_id, workflows=workflows)
        if fresh.contract_version != 2:
            raise AgentCreationDraftValidationError("legacy_draft_card_import_unsupported")
        claim_edit(db, fresh, revision)
        source = db.scalar(select(models.CharacterCardSource).where(models.CharacterCardSource.draft_id == fresh.id))
        if source is None:
            source = models.CharacterCardSource(id=uuid7_string(), owner_id=user.id, draft_id=fresh.id)
            db.add(source)
        source.source_bytes = content
        source.source_sha256 = prepared.parsed.source_sha256
        source.source_format = prepared.parsed.source_format
        source.card_version = prepared.parsed.version
        source.parser_version = prepared.parsed.parser_version
        for field, value in prepared.mapping.fields.items():
            setattr(fresh, field, value)
        fresh.source_kind = "card"
        fresh.handle = None
        fresh.avatar_temp_url = prepared.display.url if prepared.display else None
        fresh.banner_temp_url = None
        db.flush()
        if prepared.display:
            prepared.display.promote()
        return _draft_read(fresh)
    try:
        result = run_sqlite_session_immediate(db, apply, require_clean=True)
    except BaseException:
        db.rollback()
        if prepared.display:
            try:
                referenced = display_is_referenced(db, prepared.display.url)
            except Exception:
                prepared.display.finish(preserve=True)
            else:
                prepared.display.finish(remove_final=not referenced)
            finally:
                db.rollback()
        raise
    else:
        if prepared.display:
            prepared.display.finish()
    return {"draft": result, "card_version": parsed.version,
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
