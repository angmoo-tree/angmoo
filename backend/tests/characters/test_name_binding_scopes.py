from copy import deepcopy
from sqlalchemy import select, func
from sqlalchemy.orm import Session
import pytest

from app.domains.characters.models import Character
from app.contracts.name_binding import NameBindingError, read_name_binding
from app.domains.characters.service.prompt_persona import request_persona
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.service.activity_engines import bind_run
from app.domains.world_characters.service.name_binding import resolve_name_binding, validate_name_binding
from app.domains.worlds.models import WorldMembership
from tests.characters.name_binding_fixture import create_profile, rename_profile
from tests.routines.test_daily_activity_runtime import _engine, _seed, _world


def test_world_identity_freezes_per_activity_and_next_activity_uses_rename():
    with Session(_engine(), expire_on_commit=False) as db:
        world, ready, _ = _seed(db)
        profile = create_profile(db, world, ready.user.id)
        ready.character.worldview = "{{char}}는 {{user}}의 친구"
        db.commit()
        first = bind_run(db, actor=ready.world_character, activity_id="name-first")
        db.commit()
        old = read_name_binding(first.result)
        assert old.user_world_character_id == profile.world_character_id
        assert request_persona(ready.character, old)["description"].endswith("민식의 친구")
        rename_profile(db, world.id, ready.user.id, "Alex🌟")
        validate_name_binding(db, old, actor=ready.world_character, owner_id=ready.user.id)
        same = bind_run(db, actor=ready.world_character, activity_id="name-first")
        assert read_name_binding(same.result) == old
        next_run = bind_run(db, actor=ready.world_character, activity_id="name-next")
        assert read_name_binding(next_run.result).user_display_name == "Alex🌟"
        # A second World has its own active My Profile, including the same owner.
        other = _world(ready.user)
        other.id, other.slug, other.create_idempotency_key = "world-b", "world-b", "world-b"
        db.add(other); db.flush()
        member = WorldMembership(id="member-b", world_id=other.id, user_id=ready.user.id, role="owner", status="active")
        db.add(member); db.flush()
        actor_b = WorldCharacter(id="actor-b", world_id=other.id, character_id=ready.character.id,
            membership_id=member.id, status="active", control_mode="autonomous")
        db.add(actor_b); db.commit()
        second_profile = create_profile(db, other, ready.user.id, "민수")
        second = resolve_name_binding(db, actor=actor_b, owner_id=ready.user.id)
        assert second.user_display_name == "민수" and second.user_world_character_id == second_profile.world_character_id
        assert old.world_id != second.world_id and ready.character.worldview == "{{char}}는 {{user}}의 친구"
        db.get(WorldCharacter, profile.world_character_id).status = "inactive"
        db.commit()
        with pytest.raises(NameBindingError, match="scope_invalid"):
            validate_name_binding(db, old, actor=ready.world_character, owner_id=ready.user.id)


def test_resolution_does_not_create_a_missing_profile_or_change_persona():
    with Session(_engine(), expire_on_commit=False) as db:
        world, ready, _ = _seed(db)
        original = deepcopy(ready.character.worldview)
        before = db.scalar(select(func.count(Character.id)))
        snapshot = resolve_name_binding(db, actor=ready.world_character, owner_id=ready.user.id)
        assert snapshot.user_display_name is None
        assert db.scalar(select(func.count(Character.id))) == before
        assert ready.character.worldview == original
