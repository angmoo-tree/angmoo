"""SNS and Chat share the observer actor's vision binding and daily ledger."""
from datetime import UTC, datetime
from sqlalchemy import update
from app.domains.chat.models import MessageThread
from app.domains.world_characters.models import WorldCharacter
from app.domains.media.models_world_policy import WorldImagePolicy, WorldImageAttempt
from app.domains.media.contracts_vision import VisionPolicy
from app.domains.media.generation_contracts import ImagePreparationError
from app.domains.media.service import world_policy
from app.domains.identity.service.environment import installation_snapshot
from app.domains.identity.exceptions import CredentialResolutionError
from app.runtime.world_credential_binding import capture, resolve


class WorldVisionPolicies:
    def transition(self, db, request_key, state):
        states = {"submitted": "submitted", "succeeded": "completed", "failed": "failed",
            "outcome_unknown": "unknown", "released": "released"}
        if state not in states:
            raise ImagePreparationError("interpretation_attempt_state_invalid")
        db.execute(update(WorldImageAttempt).where(WorldImageAttempt.purpose == "vision",
            WorldImageAttempt.request_key == request_key).values(state=states[state]))

    def read(self, db, owner_id, asset, actor_id=None):
        if asset.scope_kind not in {"thread", "world_character", "world"}:
            raise ImagePreparationError("interpretation_scope_unavailable")
        lane = "sns"
        if asset.scope_kind == "thread":
            thread = db.get(MessageThread, asset.scope_id)
            if thread is None or thread.requester_id != owner_id or thread.deleted_at or thread.world_scope_status != "resolved":
                raise ImagePreparationError("interpretation_scope_unavailable")
            if actor_id and actor_id != thread.responding_world_character_id:
                raise ImagePreparationError("interpretation_scope_unavailable")
            actor_id, lane = thread.responding_world_character_id, "chat"
        elif asset.scope_kind == "world_character":
            if actor_id and actor_id != asset.scope_id:
                raise ImagePreparationError("interpretation_scope_unavailable")
            actor_id = asset.scope_id
        actor = db.get(WorldCharacter, actor_id) if actor_id else None
        if actor is None or (asset.scope_kind == "world" and asset.scope_id != actor.world_id):
            raise ImagePreparationError("interpretation_scope_unavailable")
        policy = db.get(WorldImagePolicy, actor.id, populate_existing=True)
        if policy is None:
            raise ImagePreparationError("world_image_policy_missing")
        try:
            binding = capture(db, owner_id=owner_id, world_id=actor.world_id, actor_id=actor.id, purpose="vision")
        except CredentialResolutionError as exc:
            raise ImagePreparationError("interpretation_key_required") from exc
        scope_key = "|".join(("world-vision.v1", actor.world_id, actor.id, binding["credential_id"], str(policy.revision), lane))
        return VisionPolicy(binding["model"], binding["thinking_level"], policy.vision_enabled,
            policy.vision_limit, binding["revision"], scope_key, f"world-vision.v1:{actor.id}",
            f"/worlds/{actor.world_id}/characters/{actor.id}?view=settings")

    def resolve(self, db, row, asset):
        parts = row.scope_key.split("|")
        if len(parts) != 6 or parts[0] != "world-vision.v1":
            raise ImagePreparationError("interpretation_binding_unproven")
        _, world, actor, key_id, revision, lane = parts
        current = self.read(db, row.owner_id, asset, actor)
        if current.scope_key != row.scope_key or not current.enabled or current.daily_limit is None:
            raise ImagePreparationError("interpretation_settings_changed")
        from app.domains.identity.service.world_credentials import find_revision
        prior = find_revision(db, owner_id=row.owner_id, world_id=world, world_character_id=actor,
            purpose="vision", credential_id=key_id, revision=row.credential_revision)
        binding = dict(version="world-credential.v1", owner_id=row.owner_id, world_id=world, actor_id=actor,
            purpose="vision", credential_id=key_id, revision=row.credential_revision,
            provider=prior.provider, model=row.model, thinking_level=row.thinking_level)
        return resolve(db, binding, owner_id=row.owner_id, world_id=world, actor_id=actor, purpose="vision")

    def available(self, db, policy):
        actor_id = policy.scope_key.split("|")[2]
        timezone = installation_snapshot(db).timezone
        return bool(policy.enabled and policy.daily_limit and world_policy.usage(db, world_character_id=actor_id,
            purpose="vision", now=datetime.now(UTC), timezone=timezone) < policy.daily_limit)

    def lock(self, db, policy):
        actor = policy.scope_key.split("|")[2]
        if db.execute(update(WorldImagePolicy).where(WorldImagePolicy.world_character_id == actor)
                .values(revision=WorldImagePolicy.revision)).rowcount != 1:
            raise ImagePreparationError("world_image_policy_missing")

    def reserve(self, db, policy, request_key):
        parts = policy.scope_key.split("|")
        world_policy.reserve(db, world_character_id=parts[2], purpose="vision", request_key=request_key,
            lane=parts[5], credential_revision=policy.credential_revision,
            now=datetime.now(UTC), timezone=installation_snapshot(db).timezone)
