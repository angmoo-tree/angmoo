"""Subject consolidation profile/key snapshots for relationship review."""
from app.runtime import world_credential_binding
from app.domains.identity.exceptions import CredentialResolutionError


def snapshot(db, scope, profile):
    try:
        binding = world_credential_binding.capture(db, owner_id=scope.owner_id, world_id=scope.world_id,
            actor_id=scope.subject_world_character_id, purpose="consolidation")
        if (binding["model"], binding["thinking_level"]) != (profile.model_id, profile.thinking_level):
            raise ValueError("profile_changed")
        return {"credential_binding": binding}
    except (CredentialResolutionError, ValueError):
        raise ValueError("relationship_review_credential_unavailable") from None


def validate(db, work, base):
    binding = base.get("credential_binding")
    if binding is None:
        raise ValueError("relationship_review_credential_binding_required")
    try:
        world_credential_binding.resolve(db, binding, owner_id=base["owner_id"], world_id=work.world_id,
            actor_id=work.actor_world_character_id, purpose="consolidation")
    except CredentialResolutionError:
        raise ValueError("relationship_review_credential_changed") from None
