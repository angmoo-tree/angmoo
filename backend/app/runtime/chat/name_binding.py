"""Chat's concrete World identity collaborator, using its caller-owned Session."""
from app.contracts.name_binding import NameBindingError, read_name_binding
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.service.name_binding import resolve_name_binding, validate_name_binding


def _actor(db, actor_id, world_id):
    actor = db.get(WorldCharacter, actor_id, populate_existing=True)
    if actor is None or actor.world_id != world_id or actor.status != "active":
        raise NameBindingError("name_binding_scope_invalid")
    return actor


def capture(db, *, owner_id, world_id, actor_id, requester_id):
    names = resolve_name_binding(db, actor=_actor(db, actor_id, world_id), owner_id=owner_id,
        requester_id=requester_id)
    return {"name_binding_policy": names.policy_version, "name_binding": names.to_dict()}


def assert_current(db, metadata, *, owner_id, world_id, actor_id):
    names = read_name_binding(metadata)
    if names is not None:
        validate_name_binding(db, names, actor=_actor(db, actor_id, world_id), owner_id=owner_id)
