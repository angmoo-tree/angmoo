"""Copy editable persona and owned display files, never identity or execution state."""
from app.config import settings
from sqlalchemy import delete
from app.domains.characters.models import CharacterCardSource
from app.domains.characters.models_import import CharacterDraftImportOrigin
from app.domains.characters.service.import_snapshots import get_import_snapshot
from app.domains.characters import schemas
from app.domains.characters.service.access import _get_owned_character
from app.domains.characters.service.creator import _draft_read
from app.domains.characters.service.drafts import _get_owned_draft, claim_edit
from app.domains.characters.service.media_storage import save_draft_profile_media_bytes
from app.integrations.media.files import media_url_to_path
from app.domains.media.contracts import InvalidProfileMediaError


def copy_settings(db, user, draft_id, data: schemas.CharacterSettingsCopy, *, workflows):
    draft = _get_owned_draft(db, user, draft_id, workflows=workflows)
    source = _get_owned_character(db, user, data.character_id)
    origin, configuration = get_import_snapshot(db, source.id)
    if workflows.validate_copy_target is not None:
        workflows.validate_copy_target(db, source.id, draft.target_world_id)
    created_files = []
    try:
        claim_edit(db, draft, data.revision)
        draft.name = configuration.profile.display_name
        draft.one_liner = configuration.profile.intro
        for field in ("personality", "speech_style", "worldview", "character_background", "topic_preferences", "safety_rules"):
            setattr(draft, field, getattr(configuration.settings, field))
        draft_origin = db.get(CharacterDraftImportOrigin, draft.id)
        if draft_origin is None:
            db.add(CharacterDraftImportOrigin(draft_id=draft.id, snapshot_id=origin.id))
        else:
            draft_origin.snapshot_id = origin.id
        draft.handle = None
        draft.source_kind = "copy"
        db.execute(delete(CharacterCardSource).where(CharacterCardSource.draft_id == draft.id, CharacterCardSource.character_id.is_(None)))
        for kind in ("avatar", "banner"):
            setattr(draft, f"{kind}_temp_url", None)
            value = getattr(configuration.profile, f"{kind}_url")
            if not value:
                continue
            try:
                path = media_url_to_path(value).resolve()
                owned = (settings.media_root_path / "characters" / origin.source_character_id).resolve()
                imported = (settings.media_root_path / "world-package-imports").resolve()
                if not path.is_relative_to(owned) and not path.is_relative_to(imported):
                    raise ValueError("unmanaged_display_media")
            except (ValueError, InvalidProfileMediaError):
                # External URLs and other identities' files are not fetched or copied.
                continue
            if path.is_file():
                content_type = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(path.suffix.lower())
                if content_type:
                    url = save_draft_profile_media_bytes(draft_id=draft.id, media_type=kind,
                        content_type=content_type, content=path.read_bytes())
                    created_files.append(media_url_to_path(url))
                    setattr(draft, f"{kind}_temp_url", url)
        db.commit()
    except Exception:
        db.rollback()
        for path in created_files:
            path.unlink(missing_ok=True)
        raise
    return _draft_read(draft)
