"""Read-only identity resolution; request owners persist the returned snapshot."""
from sqlalchemy.orm import Session

from app.contracts.name_binding import NameBindingError, NameBindingSnapshot
from app.domains.characters.service.profile import get_character
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.contracts.owner_identity import (
    LocalOwnerRequiredError, OwnerWorldRequiredError, OwnerControlledIdentityNotFoundError,
)
from app.domains.world_characters.service.owner_identity import OwnerControlledIdentityService
from app.domains.world_characters.service.configuration import effective_configuration


def resolve_name_binding(db: Session, *, actor: WorldCharacter, owner_id: str | None,
                         requester_id: str | None = None) -> NameBindingSnapshot:
    character = get_character(db, actor.character_id)
    if character is None or character.deleted_at is not None:
        raise NameBindingError("name_binding_scope_invalid")
    owner_id = owner_id or character.owner_id
    # Chat's responding character can belong to another authorized World member.
    # Autonomous actors use Character ownership; owner_user_id is nullable for
    # historical autonomous rows and is not their canonical owner field.
    if requester_id is None and character.owner_id != owner_id:
        raise NameBindingError("name_binding_scope_invalid")
    try:
        identity = OwnerControlledIdentityService(db).get(world_id=actor.world_id, current_user_id=owner_id)
    except (OwnerControlledIdentityNotFoundError, LocalOwnerRequiredError, OwnerWorldRequiredError):
        identity = None
    if requester_id is not None and (identity is None or identity.world_character_id != requester_id):
        raise NameBindingError("name_binding_requester_mismatch")
    effective_name = effective_configuration(db, world_character_id=actor.id).profile.display_name
    return NameBindingSnapshot(owner_id, actor.world_id, actor.id, effective_name,
        identity.world_character_id if identity else None,
        identity.profile.display_name if identity else None, identity.version if identity else None)


def validate_name_binding(db: Session, binding: NameBindingSnapshot, *, actor: WorldCharacter,
                          owner_id: str) -> None:
    if (binding.owner_id, binding.world_id, binding.actor_world_character_id) != (owner_id, actor.world_id, actor.id):
        raise NameBindingError("name_binding_scope_invalid")
    character = get_character(db, actor.character_id)
    if character is not None:
        db.refresh(character, attribute_names=["deleted_at"])
    if character is None or character.deleted_at is not None:
        raise NameBindingError("name_binding_scope_invalid")
    if binding.user_world_character_id is not None:
        try:
            identity = OwnerControlledIdentityService(db).get(world_id=actor.world_id, current_user_id=owner_id)
        except (OwnerControlledIdentityNotFoundError, LocalOwnerRequiredError, OwnerWorldRequiredError) as exc:
            raise NameBindingError("name_binding_scope_invalid") from exc
        if identity.world_character_id != binding.user_world_character_id:
            raise NameBindingError("name_binding_scope_invalid")
        # Renames/version changes do not invalidate a frozen authorized request.
