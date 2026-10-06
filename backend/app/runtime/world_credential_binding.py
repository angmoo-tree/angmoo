"""Freeze non-secret credential identities and resolve the same binding later."""
from app.domains.identity.service import world_credentials
from app.domains.identity.exceptions import CredentialResolutionError
from app.domains.memory.contracts.scope import MemoryScope
from app.runtime.subject_scope import read_scope_presence


def capture(db, *, owner_id, world_id, actor_id, purpose):
    if any(value is None for value in read_scope_presence(db, MemoryScope(owner_id, world_id, actor_id))):
        raise CredentialResolutionError("world_credential_scope_unavailable")
    row = world_credentials.find(db, owner_id=owner_id, world_id=world_id, world_character_id=actor_id, purpose=purpose)
    if row is None or (not row.encrypted_secret and not (purpose == "image" and row.provider == "comfyui")):
        raise CredentialResolutionError("world_credential_required")
    world_credentials.validate_profile(purpose, row.provider, row.model, row.thinking_level)
    return dict(version="world-credential.v1", owner_id=owner_id, world_id=world_id, actor_id=actor_id,
        purpose=purpose, credential_id=row.id, revision=row.revision, provider=row.provider, model=row.model, thinking_level=row.thinking_level)


def resolve(db, binding, *, owner_id, world_id, actor_id, purpose):
    if not isinstance(binding, dict) or any(value is None for value in read_scope_presence(db, MemoryScope(owner_id, world_id, actor_id))):
        raise CredentialResolutionError("world_credential_binding_changed")
    if {key: binding.get(key) for key in ("version", "owner_id", "world_id", "actor_id", "purpose")} != dict(
            version="world-credential.v1", owner_id=owner_id, world_id=world_id, actor_id=actor_id, purpose=purpose):
        raise CredentialResolutionError("world_credential_binding_changed")
    row = world_credentials.find_revision(db, owner_id=owner_id, world_id=world_id, world_character_id=actor_id,
        purpose=purpose, credential_id=binding.get("credential_id"), revision=binding.get("revision"))
    if (row.provider, row.model, row.thinking_level) != (binding.get("provider"), binding.get("model"), binding.get("thinking_level")):
        raise CredentialResolutionError("world_credential_binding_changed")
    return world_credentials.resolve(db, owner_id=owner_id, world_id=world_id, world_character_id=actor_id,
        purpose=purpose, revision=binding["revision"])
