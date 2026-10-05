"""World-owned authorization, revisions, ordering and configuration writes."""
from datetime import UTC, datetime
from sqlalchemy import select, update
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
from app.domains.world_characters.schemas import management as schemas
from app.domains.world_characters.schemas.identity import WorldCharacterProfileRead
from app.domains.world_characters.service.configuration import effective_configuration, configuration_value
from app.domains.characters.contracts import ImportProfile, ImportSettings
from app.domains.characters.exceptions import InvalidCharacterHandleError
from app.domains.characters.service.profile import normalize_character_handle
from app.domains.identity.service.owner_context import is_claimed_local_owner
from app.domains.identity.service.environment import lock_environment_admission
from app.domains.worlds.service import require_world_read_access, require_creator_access
from app.policies import name_policy


class WorldManagementError(ValueError):
    def __init__(self, reason_code, status_code=409):
        self.reason_code, self.status_code = reason_code, status_code
        super().__init__(reason_code)


class WorldCharacterManagementService:
    def __init__(self, db, *, queries, references):
        self.db, self.queries, self.references = db, queries, references

    def dashboard(self, *, world_id, user):
        world = require_world_read_access(self.db, world_id=world_id, user=user)
        rows = self.queries.public_profile_rows(self.db, world_id)
        states = self.references.states(self.db, world_id=world_id, character_ids=[character.id for _, character in rows])
        configs = {item.world_character_id: item for item in self.db.scalars(select(WorldCharacterConfiguration).where(
            WorldCharacterConfiguration.world_character_id.in_([role.id for role, _ in rows])))}
        managed_world = world.owner_user_id == user.id and is_claimed_local_owner(self.db, user.id)
        items = []
        for role, character in rows:
            stored = configs.get(role.id)
            if stored is None:
                raise WorldManagementError("world_configuration_missing")
            value = configuration_value(role, stored)
            facts = states.get(character.id, {})
            owned = managed_world and character.owner_id == user.id
            user_role = role.control_mode == "owner_controlled"
            reason = facts.get("reason") if not user_role else None
            ready = owned and not user_role and facts.get("ready", False)
            caps = schemas.WorldCharacterCapabilities(can_activate=ready and not role.autonomous_enabled,
                can_deactivate=owned and not user_role and role.autonomous_enabled,
                can_run_now=ready and not facts.get("running", False), can_edit_profile=owned,
                can_edit_settings=owned and not user_role, can_view_graph=owned,
                reason=None if ready or user_role else reason or "world_activity_not_ready")
            profile = WorldCharacterProfileRead(world_id=world_id, world_character_id=role.id, character_id=character.id,
                **value.profile.model_dump(), role_key=role.role_key, control_mode=role.control_mode,
                status="active", profile_capability="available")
            if user_role:
                status, activity = schemas.DashboardStatus(state="user"), None
            else:
                activity = schemas.DashboardActivitySettings(**{key: getattr(value.settings, key) for key in
                    ("active_hours_start", "active_hours_end", "activity_interval_minutes", "max_posts_per_day", "max_comments_per_day")}, timezone=facts.get("timezone", "UTC"))
                if not owned:
                    activity = None
                status_state, status_reason = self.references.activity_state(settings=value.settings, facts=facts)
                status = schemas.DashboardStatus(state="off" if not role.autonomous_enabled else status_state,
                    reason=None if not role.autonomous_enabled else status_reason)
            recent = facts.get("recent_activity") if not user_role and owned else None
            items.append(schemas.WorldCharacterDashboardItem(profile=profile, revision=role.version,
                autonomous_enabled=role.autonomous_enabled, status=status, settings=activity,
                next_activity_at=facts.get("next_activity_at") if owned and not user_role else None,
                recent_activity=recent, capabilities=caps))
        def order(item):
            recent = item.recent_activity.occurred_at if item.recent_activity else ""
            # Stable existing management order: ON, newest activity, name/id.
            return (item.profile.control_mode != "owner_controlled", not item.autonomous_enabled,
                -datetime.fromisoformat(recent.replace("Z", "+00:00")).timestamp() if recent else 0,
                item.profile.display_name.casefold(), item.profile.world_character_id)
        items.sort(key=order)
        users = sum(item.profile.control_mode == "owner_controlled" for item in items)
        enabled = sum(item.autonomous_enabled for item in items if item.profile.control_mode == "autonomous")
        return schemas.WorldCharacterDashboardRead(world_id=world_id, summary=schemas.WorldCharacterSummary(
            total=len(items), enabled=enabled, disabled=len(items)-users-enabled, users=users), items=items)

    def management(self, *, world_id, world_character_id, user):
        dashboard = self.dashboard(world_id=world_id, user=user)
        item = next((item for item in dashboard.items if item.profile.world_character_id == world_character_id), None)
        if item is None:
            raise WorldManagementError("world_character_not_found", 404)
        return schemas.WorldCharacterManagementRead(world_id=world_id, world_character_id=world_character_id,
            character_id=item.profile.character_id, item=item, can_manage=item.capabilities.can_edit_profile)

    def _owned_role(self, *, world_id, world_character_id, user):
        if not is_claimed_local_owner(self.db, user.id):
            raise WorldManagementError("local_owner_required", 403)
        require_creator_access(self.db, world_id=world_id, user=user)
        row = self.queries.public_profile_row(self.db, world_id, world_character_id)
        if row is None:
            raise WorldManagementError("world_character_not_found", 404)
        role, character = row
        if character.owner_id != user.id:
            raise WorldManagementError("world_character_forbidden", 403)
        return role, character

    def settings(self, *, world_id, world_character_id, user):
        role, _ = self._owned_role(world_id=world_id, world_character_id=world_character_id, user=user)
        value = effective_configuration(self.db, world_character_id=role.id)
        item = self.management(world_id=world_id, world_character_id=role.id, user=user).item
        if role.control_mode == "owner_controlled":
            raise WorldManagementError("world_character_settings_not_available", 403)
        return schemas.WorldCharacterSettingsRead(world_id=world_id, world_character_id=role.id,
            revision=role.version, profile=value.profile, settings=value.settings, capabilities=item.capabilities,
            supported_generation_models=self.references.generation_model_options(),
            supported_image_models=self.references.image_model_options(self.db, character_id=role.character_id))

    def _claim(self, role, expected_revision):
        claimed = self.db.execute(update(WorldCharacter).where(WorldCharacter.id == role.id,
            WorldCharacter.version == expected_revision, WorldCharacter.status == "active")
            .values(version=WorldCharacter.version+1).execution_options(synchronize_session="fetch"))
        if claimed.rowcount != 1:
            raise WorldManagementError("world_character_revision_conflict")

    def patch_profile(self, *, world_id, world_character_id, user, data):
        try:
            lock_environment_admission(self.db, user.id)
            role, character = self._owned_role(world_id=world_id, world_character_id=world_character_id, user=user)
            stored = self.db.get(WorldCharacterConfiguration, role.id)
            if stored is None:
                raise WorldManagementError("world_configuration_missing")
            changes = data.model_dump(exclude_unset=True, exclude={"expected_revision"})
            if "display_name" in changes:
                name = changes["display_name"].strip() if changes["display_name"] else ""
                if not name or name_policy.is_blocked_name(name):
                    raise WorldManagementError("world_profile_name_invalid", 422)
                changes["display_name"] = name
            if "handle" in changes:
                try:
                    handle = normalize_character_handle(changes["handle"] or "")
                except InvalidCharacterHandleError as error:
                    raise WorldManagementError("world_profile_handle_invalid", 422) from error
                if self.references.handle_exists(self.db, world_id=world_id, excluding=role.id, handle=handle):
                    raise WorldManagementError("world_profile_handle_conflict")
                changes["handle"] = handle
            for name in ("avatar_url", "banner_url"):
                if name in changes and changes[name] is not None and changes[name] != stored.profile.get(name):
                    self.references.validate_media(self.db, character_id=character.id, world_character_id=role.id, url=changes[name])
            profile = ImportProfile.model_validate({**stored.profile, **changes})
            self._claim(role, data.expected_revision)
            stored.profile = profile.model_dump(mode="json")
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.management(world_id=world_id, world_character_id=world_character_id, user=user)

    def patch_settings(self, *, world_id, world_character_id, user, data):
        try:
            lock_environment_admission(self.db, user.id)
            role, _ = self._owned_role(world_id=world_id, world_character_id=world_character_id, user=user)
            if role.control_mode != "autonomous":
                raise WorldManagementError("world_character_settings_not_available", 403)
            stored = self.db.get(WorldCharacterConfiguration, role.id)
            if stored is None:
                raise WorldManagementError("world_configuration_missing")
            changes = data.settings.model_dump(exclude_unset=True)
            for name in ("image_style", "appearance_prompt"):
                if name in changes and changes[name] is None:
                    changes[name] = ""
            self.references.validate_settings(self.db, character_id=role.character_id, changes=changes)
            settings = ImportSettings.model_validate({**stored.settings, **changes})
            if {"active_hours_start", "active_hours_end"} & changes.keys():
                self.references.validate_activity_settings(settings)
            self._claim(role, data.expected_revision)
            stored.settings = settings.model_dump(mode="json")
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.settings(world_id=world_id, world_character_id=world_character_id, user=user)

    def set_autonomy(self, *, world_id, world_character_id, user, data, enabled):
        try:
            lock_environment_admission(self.db, user.id)
            role, _ = self._owned_role(world_id=world_id, world_character_id=world_character_id, user=user)
            if role.control_mode != "autonomous":
                raise WorldManagementError("owner_controlled_activity_not_available", 403)
            if enabled:
                self.references.ensure_ready(self.db, character_id=role.character_id, world_id=world_id, user=user)
            self._claim(role, data.expected_revision)
            role.autonomous_enabled = enabled
            # Saved World intent does not write global Agent settings/status or
            # cancel an already admitted run. Existing scheduler owns resources.
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.dashboard(world_id=world_id, user=user)
