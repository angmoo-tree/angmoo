"""Existing validated file storage plus owning World CAS, with compensation."""
from app.domains.characters.service.media_storage import save_profile_media
from app.domains.world_characters.schemas.management import WorldCharacterProfilePatch
from app.domains.world_characters.service.management import WorldManagementError
from app.domains.identity.service.environment import lock_environment_admission
from app.integrations.media.files import media_url_to_path


def upload_profile_media(service, *, world_id, world_character_id, user, data):
    db = service.db
    lock_environment_admission(db, user.id)
    role, character = service._owned_role(world_id=world_id, world_character_id=world_character_id, user=user)
    if role.version != data.expected_revision:
        db.rollback()
        raise WorldManagementError("world_character_revision_conflict")
    path = None
    try:
        url = save_profile_media(character_id=character.id, media_type=data.media_type,
            content_type=data.content_type, data_base64=data.data_base64)
        path = media_url_to_path(url)
        return service.patch_profile(world_id=world_id, world_character_id=world_character_id, user=user,
            data=WorldCharacterProfilePatch(expected_revision=data.expected_revision, **{f"{data.media_type}_url": url}))
    except Exception:
        db.rollback()
        if path:
            path.unlink(missing_ok=True)
        raise
