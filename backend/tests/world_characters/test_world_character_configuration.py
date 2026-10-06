"""Actual owning routes/storage/CAS/public values across two independent Worlds."""
import json
from datetime import UTC, datetime
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select, update
from sqlalchemy.orm import Session
from app.api.identity_dependencies import get_current_user
from app.database import get_db
from app.domains.world_characters.router.management import router
from app.domains.world_characters.service.management import WorldManagementError
from app.runtime.world_characters.management import management_service
from app.domains.world_characters.schemas.management import WorldCharacterProfilePatch, WorldCharacterSettingsPatch, ExpectedWorldRevision
from app.domains.world_characters.service.configuration import effective_configuration
from app.domains.world_characters.service.owner_identity import OwnerControlledIdentityService
from app.domains.world_characters.schemas.identity import MyProfilePatch
from app.domains.characters.models import Character
from app.domains.characters.models_import import CharacterImportSnapshot, CharacterImportOrigin
from app.domains.world_characters.models import WorldCharacter, CharacterActiveWorld, CharacterWorldBinding
from app.domains.routines.models import AgentActivitySetting
from world_configuration_fixture_support import seed_configuration_fixture, fixture_owner, install_configuration_image_fixture


@pytest.fixture
def engine(tmp_path):
    value = seed_configuration_fixture(tmp_path / "world-config.sqlite3")
    yield value
    value.dispose()


def _client(engine):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    def db_dependency():
        with Session(engine) as db:
            yield db
    def owner_dependency():
        with Session(engine) as db:
            owner = fixture_owner(db)
            db.expunge(owner)
            return owner
    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_current_user] = owner_dependency
    return TestClient(app, base_url="http://127.0.0.1:3000")


def test_t49_t53_dashboard_partition_user_first_read_only_and_no_private_values(engine):
    with Session(engine) as db:
        owner = fixture_owner(db)
        before = [(row.id, row.version, row.autonomous_enabled) for row in db.scalars(select(WorldCharacter))]
        origin_before = [(row.id, row.digest, row.payload) for row in db.scalars(select(CharacterImportSnapshot))]
        dashboard = management_service(db).dashboard(world_id="config-world-a", user=owner)
        assert dashboard.summary.model_dump() == {"total": 2, "enabled": 0, "disabled": 1, "users": 1}
        assert dashboard.items[0].profile.control_mode == "owner_controlled"
        assert dashboard.items[0].settings is None and dashboard.items[0].recent_activity is None
        assert dashboard.items[1].profile.world_id == "config-world-a"
        assert "Original persona" not in dashboard.model_dump_json()
        assert "encrypted" not in dashboard.model_dump_json() and "fixture-owner" not in dashboard.model_dump_json()
        assert before == [(row.id, row.version, row.autonomous_enabled) for row in db.scalars(select(WorldCharacter))]
        assert origin_before == [(row.id, row.digest, row.payload) for row in db.scalars(select(CharacterImportSnapshot))]
        assert not db.new and not db.dirty


def test_t89_t90_world_settings_profile_and_explicit_removals_never_write_source_or_other_world(engine):
    with Session(engine) as db:
        owner = fixture_owner(db)
        source = db.get(Character, "config-actor-a")
        original = (source.name, source.personality, source.one_liner, source.handle)
        origin = db.get(CharacterImportSnapshot, db.get(CharacterImportOrigin, source.id).snapshot_id)
        digest = origin.digest
        service = management_service(db)
        image_model = install_configuration_image_fixture(db, character_id=source.id)
        service.patch_profile(world_id="config-world-a", world_character_id="config-role-a", user=owner,
            data=WorldCharacterProfilePatch(expected_revision=1, display_name="A's Bram", handle="world_bram", intro="", avatar_url=None, banner_url=None))
        service.patch_settings(world_id="config-world-a", world_character_id="config-role-a", user=owner,
            data=WorldCharacterSettingsPatch(expected_revision=2, settings={"personality": "World A persona", "active_hours_start": "11:00",
                "activity_interval_minutes": 45, "generation_model": "gemini-3.5-flash-lite", "image_model": image_model, "image_style": "soft"}))
        a = effective_configuration(db, world_character_id="config-role-a")
        b = effective_configuration(db, world_character_id="config-role-b")
        assert a.profile.display_name == "A's Bram" and a.profile.intro == "" and a.profile.avatar_url is None
        assert a.settings.personality == "World A persona" and a.settings.activity_interval_minutes == 45
        assert a.settings.image_model == image_model and a.settings.image_style == "soft" and b.settings.image_model is None
        assert b.profile.display_name == "Bram" and b.settings.personality == "Original persona" and b.revision == 1
        assert (source.name, source.personality, source.one_liner, source.handle) == original
        assert origin.digest == digest and origin.payload["settings"]["personality"] == "Original persona"
        source.name, source.personality, source.one_liner = "Global edited", "Global changed", "Global intro"
        source.avatar_url = "https://example.test/global.png"
        db.commit()
        a = effective_configuration(db, world_character_id="config-role-a")
        b = effective_configuration(db, world_character_id="config-role-b")
        assert a.profile.intro == "" and a.profile.avatar_url is None
        assert b.profile.display_name == "Bram" and b.settings.personality == "Original persona"


def test_t95_route_auth_origin_scope_fields_and_revision_fail_without_writes(engine):
    client = _client(engine)
    prefix = "/api/v1/worlds/config-world-a/world-characters/config-role-a"
    headers = {"Origin": "http://127.0.0.1:3000"}
    assert client.get(prefix + "/settings").status_code == 200
    assert client.patch(prefix + "/settings", json={"expected_revision": 1, "settings": {"personality": "No origin"}}).status_code == 403
    for payload in ({"expected_revision": 1, "credential": "fake"}, {"expected_revision": 1, "source_snapshot": "fake"},
                    {"expected_revision": 1, "settings": {"auto_enabled": True}}, {"expected_revision": 1, "settings": {"generation_model": "unsupported"}},
                    {"expected_revision": 1, "settings": {"active_hours_start": "24:30"}}):
        assert client.patch(prefix + "/settings", headers=headers, json=payload).status_code == 422
    assert client.patch(prefix + "/profile", headers=headers, json={"expected_revision": 1, "avatar_url": "https://example.test/not-owned.png"}).status_code == 422
    assert client.patch(prefix.replace("config-role-a", "config-role-b") + "/profile", headers=headers, json={"expected_revision": 1, "intro": "cross"}).status_code == 404
    assert client.patch(prefix + "/profile", headers=headers, json={"expected_revision": 77, "intro": "conflict"}).json() == {"detail": "world_character_revision_conflict"}
    with Session(engine) as db:
        assert db.get(WorldCharacter, "config-role-a").version == 1
        assert effective_configuration(db, world_character_id="config-role-a").profile.intro == "Original intro"


def test_t89_world_handle_uses_canonical_policy_without_rewriting_unchanged_user_handle(engine):
    with Session(engine) as db:
        owner = fixture_owner(db)
        user_role = db.scalar(select(WorldCharacter).where(
            WorldCharacter.world_id == "config-world-a", WorldCharacter.control_mode == "owner_controlled"))
        original_handle = effective_configuration(db, world_character_id=user_role.id).profile.handle
        source_handle = db.get(Character, user_role.character_id).handle
        service = management_service(db)
        service.patch_profile(world_id="config-world-a", world_character_id=user_role.id, user=owner,
            data=WorldCharacterProfilePatch(expected_revision=user_role.version, intro="World user intro"))
        assert effective_configuration(db, world_character_id=user_role.id).profile.handle == original_handle
        assert db.get(Character, user_role.character_id).handle == source_handle
        service.patch_profile(world_id="config-world-a", world_character_id="config-role-a", user=owner,
            data=WorldCharacterProfilePatch(expected_revision=1, handle=" @Bram-New "))
        assert effective_configuration(db, world_character_id="config-role-a").profile.handle == "bram_new"
        for value in ("x", "a" * 41, "invalid!"):
            with pytest.raises(WorldManagementError, match="world_profile_handle_invalid"):
                service.patch_profile(world_id="config-world-a", world_character_id="config-role-a", user=owner,
                    data=WorldCharacterProfilePatch(expected_revision=2, handle=value))
        with pytest.raises(WorldManagementError, match="world_profile_handle_conflict"):
            service.patch_profile(world_id="config-world-a", world_character_id=user_role.id, user=owner,
                data=WorldCharacterProfilePatch(expected_revision=user_role.version, handle="bram_new"))
        assert effective_configuration(db, world_character_id="config-role-a").revision == 2
        assert db.get(Character, "config-actor-a").handle == "bram_a"


def test_t96_two_sessions_same_revision_exactly_one_success_and_one_conflict(engine):
    barrier = Barrier(2)
    def save(text):
        with Session(engine) as db:
            owner = fixture_owner(db)
            barrier.wait()
            try:
                value = management_service(db).patch_profile(world_id="config-world-a", world_character_id="config-role-a", user=owner,
                    data=WorldCharacterProfilePatch(expected_revision=1, intro=text))
                return value.item.revision
            except WorldManagementError as exc:
                return exc.reason_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(save, ("first", "second")))
    assert sorted(values, key=str) == [2, "world_character_revision_conflict"]
    with Session(engine) as db:
        assert db.get(WorldCharacter, "config-role-a").version == 2
        assert effective_configuration(db, world_character_id="config-role-b").revision == 1


def test_t97_owner_world_profile_alias_writes_world_only_and_name_binding(engine):
    from app.domains.world_characters.service.name_binding import resolve_name_binding
    with Session(engine) as db:
        owner = fixture_owner(db)
        service = OwnerControlledIdentityService(db)
        identity = service.get(world_id="config-world-a", current_user_id=owner.id)
        character = db.get(Character, identity.character_id)
        before = (character.name, character.handle, character.one_liner)
        updated = service.patch(world_id="config-world-a", current_user_id=owner.id,
            data=MyProfilePatch(version=identity.version, display_name="World User", handle="world_user", intro="Scoped intro"))
        assert updated.profile.display_name == "World User" and updated.profile.handle == "world_user"
        assert (character.name, character.handle, character.one_liner) == before
        actor = db.get(WorldCharacter, "config-role-a")
        names = resolve_name_binding(db, actor=actor, owner_id=owner.id, requester_id=identity.world_character_id)
        assert names.user_display_name == "World User"


def test_t103_t105_independent_ids_default_off_saved_onoff_never_write_global_flags(engine, monkeypatch):
    with Session(engine) as db:
        owner = fixture_owner(db)
        service = management_service(db)
        monkeypatch.setattr(service.references, "ensure_ready", lambda *_args, **_kwargs: None)
        origins = [db.get(CharacterImportOrigin, f"config-actor-{suffix}").snapshot_id for suffix in ("a", "b")]
        assert origins[0] == origins[1]
        for suffix in ("a", "b"):
            role = db.get(WorldCharacter, f"config-role-{suffix}")
            assert not role.autonomous_enabled
            assert db.get(CharacterWorldBinding, role.character_id).world_id == role.world_id
            assert db.get(CharacterActiveWorld, role.character_id).world_character_id == role.id
            service.set_autonomy(world_id=role.world_id, world_character_id=role.id, user=owner,
                data=ExpectedWorldRevision(expected_revision=1), enabled=True)
        assert all(db.get(WorldCharacter, f"config-role-{suffix}").autonomous_enabled for suffix in ("a", "b"))
        service.set_autonomy(world_id="config-world-a", world_character_id="config-role-a", user=owner,
            data=ExpectedWorldRevision(expected_revision=2), enabled=False)
        assert not db.get(WorldCharacter, "config-role-a").autonomous_enabled
        assert db.get(WorldCharacter, "config-role-b").autonomous_enabled
        assert all(not db.get(AgentActivitySetting, f"config-actor-{suffix}").auto_enabled for suffix in ("a", "b"))


def test_t91_snapshot_immutable_and_payload_contains_configuration_only(engine):
    with Session(engine) as db:
        snapshot = db.scalar(select(CharacterImportSnapshot).where(CharacterImportSnapshot.source_character_id == "config-actor-a"))
        assert snapshot.kind == "creation" and snapshot.contract_version == 1
        assert set(snapshot.payload) == {"profile", "settings"}
        assert not any(word in json.dumps(snapshot.payload).lower() for word in ("credential", "encrypted", "memory", "lease", "auto_enabled", "world_id"))
        snapshot.kind = "legacy_transition"
        with pytest.raises(ValueError, match="snapshot_immutable"):
            db.commit()
        db.rollback()


def test_t93_explicit_entry_initializes_existing_basis_once_and_get_never_backfills(engine):
    from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
    from app.runtime.world_characters.creation_configuration import initialize_entered_world_character
    from app.domains.world_characters.exceptions import WorldCharacterSetupValidationError
    with Session(engine) as db:
        owner = fixture_owner(db)
        role = db.get(WorldCharacter, "config-role-a")
        basis_id = db.get(CharacterImportOrigin, role.character_id).snapshot_id
        db.delete(db.get(WorldCharacterConfiguration, role.id))
        db.commit()
        with pytest.raises(WorldManagementError, match="world_configuration_missing"):
            management_service(db).dashboard(world_id=role.world_id, user=owner)
        assert db.get(WorldCharacterConfiguration, role.id) is None
        initialize_entered_world_character(db, world_character_id=role.id)
        db.commit()
        stored = db.get(WorldCharacterConfiguration, role.id)
        assert stored.snapshot_id == basis_id
        assert stored.profile["display_name"] == "Bram" and role.version == 1
        stored.profile = {**stored.profile, "intro": "World-local edit"}
        role.version = 2
        role.autonomous_enabled = True
        db.commit()
        initialize_entered_world_character(db, world_character_id=role.id)
        db.commit()
        assert stored.profile["intro"] == "World-local edit"
        assert role.version == 2 and role.autonomous_enabled
        with pytest.raises(WorldCharacterSetupValidationError, match="world_character_not_ready"):
            initialize_entered_world_character(db, world_character_id="missing-role")


def test_t53_recent_activity_requires_current_world_evidence_and_orders_by_time(engine):
    from app.domains.social.models.posts import Post
    from app.domains.routines.models import AgentActivityLog
    with Session(engine) as db:
        owner = fixture_owner(db)
        for suffix in ("a", "b"):
            db.add(Post(id=f"recent-{suffix}", author_character_id=f"config-actor-{suffix}",
                author_world_character_id=f"config-role-{suffix}", world_id=f"config-world-{suffix}",
                author_name="Bram", title=f"World {suffix} post", body="Fixture"))
        db.flush()
        db.add_all([
            AgentActivityLog(user_id=owner.id, character_id="config-actor-a", action_type="post",
                target_post_id="recent-a", created_at=datetime(2026, 10, 5, 12, 0, tzinfo=UTC)),
            AgentActivityLog(user_id=owner.id, character_id="config-actor-a", action_type="like",
                target_post_id="recent-b", created_at=datetime(2026, 10, 5, 14, 0, tzinfo=UTC)),
            AgentActivityLog(user_id=owner.id, character_id="config-actor-a", action_type="legacy_global",
                target_post_id=None, created_at=datetime(2026, 10, 5, 15, 0, tzinfo=UTC)),
            AgentActivityLog(user_id=owner.id, character_id="config-actor-a", action_type="older-post",
                target_post_id="recent-a", created_at=datetime(2026, 10, 5, 11, 0, tzinfo=UTC)),
        ])
        db.commit()
        item = next(item for item in management_service(db).dashboard(world_id="config-world-a", user=owner).items
            if item.profile.world_character_id == "config-role-a")
        assert item.recent_activity.action_type == "post"
        assert item.recent_activity.post_id == "recent-a" and item.recent_activity.title == "World a post"
        assert datetime.fromisoformat(item.recent_activity.occurred_at) == datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def test_t56_dashboard_batch_queries_do_not_grow_per_character(engine):
    from app.domains.worlds.models import WorldMembership
    from app.runtime.world_characters.creation_configuration import initialize_created_world_character
    statements = []
    def count_query(*_args):
        statements.append(1)
    event.listen(engine, "before_cursor_execute", count_query)
    with Session(engine) as db:
        owner = fixture_owner(db)
        statements.clear()
        initial = management_service(db).dashboard(world_id="config-world-a", user=owner)
        first_count = len(statements)
        membership = db.scalar(select(WorldMembership).where(WorldMembership.world_id == "config-world-a",
            WorldMembership.user_id == owner.id))
        for index in range(7):
            character = Character(id=f"extra-actor-{index}", owner_id=owner.id, name=f"Extra {index}",
                handle=f"extra-{index}", personality="Fixture", speech_style="Fixture", worldview="Fixture",
                one_liner="Fixture", persona_summary="Fixture", moderation_status="active", execution_mode="llm")
            db.add(character)
            db.flush()
            role = WorldCharacter(id=f"extra-role-{index}", world_id="config-world-a", character_id=character.id,
                membership_id=membership.id, role_key="resident", status="active", control_mode="autonomous",
                activity_runtime_mode="routine_resident_v1", character_contract_hash="a" * 64, world_contract_hash="a" * 64)
            db.add(role)
            db.flush()
            initialize_created_world_character(db, character=character, world_character=role)
            db.add(CharacterActiveWorld(character_id=character.id, world_character_id=role.id,
                selected_at=datetime.now(UTC), idempotency_key=f"extra-select-{index}"))
        db.commit()
        db.refresh(owner)
        statements.clear()
        expanded = management_service(db).dashboard(world_id="config-world-a", user=owner)
        assert len(expanded.items) == len(initial.items) + 7
        assert len(statements) == first_count
        assert first_count <= 22
    event.remove(engine, "before_cursor_execute", count_query)


def test_t49_t52_dashboard_filters_participation_and_counts_zero_and_multiple_users(engine):
    from app.domains.worlds.models import WorldMembership
    from app.runtime.world_characters.creation_configuration import initialize_created_world_character
    from sqlalchemy.exc import IntegrityError
    with Session(engine) as db:
        owner = fixture_owner(db)
        a = db.get(WorldCharacter, "config-role-a")
        b = db.get(WorldCharacter, "config-role-b")
        a.autonomous_enabled = True
        db.get(AgentActivitySetting, a.character_id).auto_enabled = False
        b.autonomous_enabled = True
        owner_role = db.scalar(select(WorldCharacter).where(WorldCharacter.world_id == a.world_id,
            WorldCharacter.control_mode == "owner_controlled"))
        owner_role.status = "inactive"
        unrelated = Character(id="unjoined-local", owner_id=owner.id, name="Local only", handle="unjoined_local",
            personality="Private local persona", speech_style="Local", worldview="Local", persona_summary="Local")
        db.add(unrelated)
        extra_ids = []
        for label in ("user", "suspended", "deleted", "inactive", "left-membership", "wrong-membership"):
            character = Character(id=f"participation-{label}", owner_id=owner.id, name="사용자" if label == "user" else label,
                handle=f"participation_{label.replace('-', '_')}", personality="Private participant persona",
                speech_style="Fixture", worldview="Fixture", persona_summary="Fixture")
            db.add(character)
            db.flush()
            member_id = a.membership_id
            if label == "left-membership":
                member = WorldMembership(id="participation-left", world_id=a.world_id, user_id="fixture-outsider",
                    role="member", status="left", joined_at=datetime.now(UTC))
                db.add(member)
                db.flush()
                member_id = member.id
            if label == "wrong-membership":
                member_id = b.membership_id
            role = WorldCharacter(id=f"participation-role-{label}", world_id=a.world_id, character_id=character.id,
                membership_id=member_id, role_key="no_specific_role", control_mode="autonomous",
                status="inactive" if label == "inactive" else "active", autonomous_enabled=False,
                activity_runtime_mode="routine_resident_v1")
            if label == "wrong-membership":
                with pytest.raises(IntegrityError):
                    with db.begin_nested():
                        db.add(role)
                        db.flush()
                continue
            db.add(role)
            db.flush()
            initialize_created_world_character(db, character=character, world_character=role)
            if label == "suspended":
                character.moderation_status = "suspended"
            if label == "deleted":
                character.deleted_at = datetime.now(UTC)
            extra_ids.append(role.id)
        db.commit()
        service = management_service(db)
        zero = service.dashboard(world_id=a.world_id, user=owner)
        assert zero.summary.model_dump() == {"total": 2, "enabled": 1, "disabled": 1, "users": 0}
        assert {item.profile.world_character_id for item in zero.items} == {a.id, extra_ids[0]}
        assert zero.items[0].profile.world_character_id == a.id
        assert zero.items[1].profile.control_mode == "autonomous"
        assert zero.items[1].profile.display_name == "사용자"
        from app.domains.identity.models import User
        other_user = User(id="participation-owner", email="participant@example.test", display_name="Participant",
            display_name_normalized="participant", privacy_policy_version="test", terms_version="test",
            profile_setup_completed=True)
        db.add(other_user)
        db.flush()
        other_member = WorldMembership(id="participation-owner-member", world_id=a.world_id, user_id=other_user.id,
            role="member", status="active", joined_at=datetime.now(UTC))
        db.add(other_member)
        db.flush()
        owner_role.status = "active"
        other_role = db.get(WorldCharacter, extra_ids[0])
        other_role.control_mode = "owner_controlled"
        other_role.owner_user_id = other_user.id
        other_role.membership_id = other_member.id
        db.get(Character, other_role.character_id).owner_id = other_user.id
        db.commit()
        multiple = service.dashboard(world_id=a.world_id, user=owner)
        assert multiple.summary.model_dump() == {"total": 3, "enabled": 1, "disabled": 0, "users": 2}
        assert all(item.profile.control_mode == "owner_controlled" for item in multiple.items[:2])
        assert multiple.items[-1].profile.world_character_id == a.id
        assert "Private" not in multiple.model_dump_json()
        assert service.dashboard(world_id=b.world_id, user=owner).summary.enabled == 1
        assert not db.dirty and not db.new


def test_t57_t107_dashboard_keeps_saved_on_across_hours_capacity_running_error_and_readiness(engine, monkeypatch):
    from datetime import timedelta
    from app.domains.routines.models import AgentSlot
    from app.domains.identity.models import LlmCredential
    from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
    from app.runtime.world_characters import management as runtime
    now = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz) if tz else now.replace(tzinfo=None)
    monkeypatch.setattr(runtime, "datetime", Clock)
    with Session(engine) as db:
        owner = fixture_owner(db)
        role = db.get(WorldCharacter, "config-role-a")
        role.autonomous_enabled = True
        role.activity_runtime_mode = "legacy_resident_v1"
        stored = db.get(WorldCharacterConfiguration, role.id)
        stored.settings = {**stored.settings, "active_hours_start": "09:00", "active_hours_end": "02:00"}
        db.commit()
        service = management_service(db)
        def state(expected):
            dashboard = service.dashboard(world_id=role.world_id, user=owner)
            item = next(value for value in dashboard.items if value.profile.world_character_id == role.id)
            assert item.status.state == expected
            assert item.autonomous_enabled and dashboard.summary.enabled == 1
            assert db.get(AgentActivitySetting, role.character_id).auto_enabled is False
            assert db.get(WorldCharacter, "config-role-b").autonomous_enabled is False
            assert not db.new and not db.dirty
            return item
        assert state("capacity_wait").next_activity_at is None
        slot = AgentSlot(agent_id="dashboard-state-slot", status="idle", assigned_character_id=role.character_id,
            assigned_user_id=owner.id, assigned_credential_id="config-credential-a", next_tick_at=now + timedelta(minutes=30))
        db.add(slot)
        db.commit()
        assert state("waiting").next_activity_at is not None
        slot.status, slot.lease_expires_at = "running", now + timedelta(minutes=5)
        db.commit()
        state("running")
        slot.status, slot.lease_expires_at, slot.last_error = "idle", None, "synthetic_activity_failure"
        db.commit()
        state("error")
        slot.last_error = None
        stored.settings = {**stored.settings, "active_hours_start": "00:00", "active_hours_end": "00:30"}
        db.commit()
        state("outside_hours")
        db.get(LlmCredential, "config-credential-a").enabled = False
        db.commit()
        assert state("not_ready").status.reason == "credential_required"
