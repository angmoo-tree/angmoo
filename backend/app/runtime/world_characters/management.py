"""Same-session batch facts and supported Routine/Media adapters for World UI."""
from datetime import UTC, datetime
from sqlalchemy import select, func
from app.domains.characters.models import Character
from app.domains.identity.models import LlmCredential
from app.domains.identity.service.environment import snapshot
from app.domains.routines.models import AgentActivitySetting, AgentActivityLog, AgentSlot, AgentRun
from app.domains.social.models.posts import Post
from app.domains.worlds.service import get_world
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
from app.domains.world_characters.service.management import WorldCharacterManagementService, WorldManagementError
from app.domains.world_characters.service.readiness import evaluate, evaluate_many
from app.runtime.world_characters.queries import SqlAlchemyWorldCharacterQueries


class SqlAlchemyWorldManagementReferences:
    def generation_model_options(self):
        from app.providers.generation_profiles import GENERATION_MODELS
        return [{"value": model, "label": model, "enabled": True, "reason": None} for model in GENERATION_MODELS]

    def states(self, db, *, world_id, character_ids):
        if not character_ids:
            return {}
        world = get_world(db, world_id)
        characters = list(db.scalars(select(Character).where(Character.id.in_(character_ids))))
        activity = {s.character_id: s for s in db.scalars(select(AgentActivitySetting).where(AgentActivitySetting.character_id.in_(character_ids)))}
        readiness = evaluate_many(db, characters=characters, activity_settings=activity, world_id=world_id)
        credential_ids = set(db.scalars(select(LlmCredential.character_id).where(LlmCredential.character_id.in_(character_ids), LlmCredential.enabled.is_(True))))
        all_slots = list(db.scalars(select(AgentSlot)))
        slots = {s.assigned_character_id: s for s in all_slots if s.assigned_character_id in character_ids}
        # A legacy global log without a scoped post cannot establish a World.
        # Rank current-World evidence by its actual timestamp, then stable ID.
        latest = select(AgentActivityLog.id, func.row_number().over(
            partition_by=AgentActivityLog.character_id,
            order_by=(AgentActivityLog.created_at.desc(), AgentActivityLog.id.desc())).label("position")).join(
            Post, Post.id == AgentActivityLog.target_post_id).where(
            AgentActivityLog.character_id.in_(character_ids), Post.world_id == world_id).subquery()
        logs = {log.character_id: (log, post) for log, post in db.execute(select(AgentActivityLog, Post).join(
            latest, latest.c.id == AgentActivityLog.id).join(Post, Post.id == AgentActivityLog.target_post_id).where(
            latest.c.position == 1)).all()}
        from app.config import settings
        from app.domains.routines.service.tick_schedule import aware_utc
        environment = snapshot(db, world.owner_user_id)
        capacity_full = all(slot.assigned_character_id is not None for slot in all_slots) if all_slots else True
        result = {}
        for character in characters:
            setting = activity.get(character.id)
            ready = character.execution_mode == "llm" and character.id in credential_ids and readiness[character.id].ready
            slot = slots.get(character.id)
            running = bool(slot and slot.status == "running" and slot.lease_expires_at and aware_utc(slot.lease_expires_at) > datetime.now(UTC))
            log_post = logs.get(character.id)
            recent = None
            if log_post:
                log, post = log_post
                # Never link a private/deleted/other-World post from a card.
                accessible = post and post.world_id == world_id and post.deleted_at is None and post.visibility == "public"
                recent = {"action_type": log.action_type, "occurred_at": aware_utc(log.created_at).isoformat(),
                    "post_id": post.id if accessible else None, "title": post.title if accessible else None}
            result[character.id] = {"ready": ready, "running": running, "timezone": environment.timezone,
                "capacity_wait": slot is None and capacity_full, "last_error": slot.last_error if slot else None,
                "reason": None if ready else "credential_required" if character.id not in credential_ids else readiness[character.id].reason_code or "world_activity_not_ready",
                "next_activity_at": aware_utc(slot.next_tick_at).isoformat() if slot and slot.next_tick_at else None, "recent_activity": recent}
        return result

    def activity_state(self, *, settings, facts):
        from zoneinfo import ZoneInfo
        from app.domains.routines.service.tick_schedule import is_within_active_hours
        if facts.get("running"):
            return "running", None
        if not facts.get("ready"):
            return "not_ready", facts.get("reason") or "world_activity_not_ready"
        if not is_within_active_hours(settings, datetime.now(UTC), timezone=ZoneInfo(facts.get("timezone", "UTC"))):
            return "outside_hours", "outside_active_hours"
        if facts.get("last_error") not in (None, "world_active_hours_waiting", "world_autonomy_disabled"):
            return "error", "activity_error"
        if facts.get("capacity_wait"):
            return "capacity_wait", "waiting_capacity"
        return "waiting", "execution_wait"

    def handle_exists(self, db, *, world_id, excluding, handle):
        rows = db.execute(select(WorldCharacter.id, WorldCharacterConfiguration.profile).join(WorldCharacterConfiguration,
            WorldCharacterConfiguration.world_character_id == WorldCharacter.id).where(WorldCharacter.world_id == world_id,
            WorldCharacter.id != excluding, WorldCharacter.status == "active")).all()
        return any(profile.get("handle", "").casefold() == handle.casefold() for _, profile in rows)

    def validate_media(self, db, *, character_id, world_character_id, url):
        from app.config import settings
        from app.integrations.media.files import media_url_to_path
        from app.domains.media.contracts import InvalidProfileMediaError
        try:
            path = media_url_to_path(url).resolve()
            owned = (settings.media_root_path / "characters" / character_id).resolve()
            if not path.is_relative_to(owned) or not path.is_file():
                raise ValueError("world_profile_media_not_owned")
        except (ValueError, OSError, InvalidProfileMediaError) as exc:
            raise WorldManagementError("world_profile_media_not_owned", 422) from exc

    def validate_settings(self, db, *, character_id, changes):
        from app.providers.generation_profiles import GENERATION_MODELS
        from app.domains.characters.service.creator import _ensure_draft_persona_prompt_safety
        _ensure_draft_persona_prompt_safety({key: value for key, value in changes.items() if key in
            ("personality", "speech_style", "worldview", "character_background", "topic_preferences", "safety_rules")})
        if changes.get("generation_model") is not None and changes["generation_model"] not in GENERATION_MODELS:
            raise WorldManagementError("generation_profile_unsupported", 422)
        if changes.get("image_model") is not None:
            from app.domains.characters.models import AgentImageGenerationSetting
            from app.domains.characters.service.world_image_profiles import select_world_image_profile
            from app.domains.media.generation_contracts import ImagePreparationError
            setting = db.get(AgentImageGenerationSetting, character_id)
            try:
                if setting is None:
                    raise ImagePreparationError("world_image_model_connection_unverified")
                select_world_image_profile(setting, changes["image_model"])
            except ValueError as exc:
                raise WorldManagementError("world_image_model_connection_unverified", 422) from exc

    def validate_activity_settings(self, settings):
        """Compose the existing Routine policy without importing it in World schemas."""
        from app.domains.routines.policies.active_hours import validate_active_hours
        try:
            validate_active_hours(settings.active_hours_start, settings.active_hours_end)
        except ValueError as exc:
            raise WorldManagementError("world_active_hours_invalid", 422) from exc

    def image_model_options(self, db, *, character_id):
        from app.domains.characters.models import AgentImageGenerationSetting
        from app.domains.characters.service.world_image_profiles import available_world_image_models
        return available_world_image_models(db.get(AgentImageGenerationSetting, character_id))

    def ensure_ready(self, db, *, character_id, world_id, user):
        from app.domains.identity.repository.credentials import get_character_credential
        character = db.get(Character, character_id)
        setting = db.get(AgentActivitySetting, character_id)
        if character is None or setting is None or character.execution_mode != "llm":
            raise WorldManagementError("world_activity_not_ready")
        ready = evaluate(db, character=character, setting=setting)
        if not ready.ready or ready.world_id != world_id:
            raise WorldManagementError(ready.reason_code or "world_activity_not_ready")
        credential = get_character_credential(db, character_id)
        if credential is None or not credential.enabled:
            raise WorldManagementError("credential_required")
        from app.domains.operations.service import maintenance as maintenance_service
        maintenance_service.ensure_auto_ticks_available(db)


def management_service(db):
    return WorldCharacterManagementService(db, queries=SqlAlchemyWorldCharacterQueries(), references=SqlAlchemyWorldManagementReferences())
