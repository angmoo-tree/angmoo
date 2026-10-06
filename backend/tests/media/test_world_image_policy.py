from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.domains.media.contracts import ImagePreparationError
from app.domains.media.models_world_policy import WorldImagePolicy
from app.domains.media.service import world_policy
from world_configuration_fixture_support import seed_configuration_fixture


def test_new_actor_defaults_are_saved_off_and_legacy_null_is_not_repaired(tmp_path, deny_external_network):
    engine = seed_configuration_fixture(tmp_path / "policy.sqlite3")
    with Session(engine) as db:
        row = db.get(WorldImagePolicy, "config-role-a")
        assert (row.generation_limit, row.vision_limit, row.generation_enabled, row.vision_enabled) == (20, 10, False, False)
        row.generation_limit = row.vision_limit = None
        db.flush()
        assert world_policy.initialize_new_actor(db, world_character_id=row.world_character_id).generation_limit is None
    engine.dispose()


def test_sns_chat_share_vision_cap_but_not_generation_and_rotation_keeps_usage(tmp_path, deny_external_network):
    engine = seed_configuration_fixture(tmp_path / "usage.sqlite3")
    now = datetime(2026, 10, 6, 8, tzinfo=UTC)
    with Session(engine) as db:
        actor = "config-role-a"
        world_policy.patch(db, world_character_id=actor, expected_revision=1,
            changes={"vision_limit": 2, "vision_enabled": True, "generation_enabled": True}, require_key=lambda purpose: True)
        base = dict(world_character_id=actor, purpose="vision", credential_revision=1, now=now, timezone="Asia/Seoul")
        first = world_policy.reserve(db, **base, request_key="one", lane="sns")
        assert world_policy.reserve(db, **base, request_key="one", lane="sns").id == first.id
        world_policy.reserve(db, **base, request_key="two", lane="chat")
        with pytest.raises(ImagePreparationError, match="daily_limit"):
            world_policy.reserve(db, **{**base, "credential_revision": 2}, request_key="three", lane="chat")
        assert world_policy.usage(db, world_character_id=actor, purpose="vision", now=now, timezone="Asia/Seoul") == 2
        assert world_policy.usage(db, world_character_id=actor, purpose="image", now=now, timezone="Asia/Seoul") == 0
        assert world_policy.usage(db, world_character_id="config-role-b", purpose="vision", now=now, timezone="Asia/Seoul") == 0
    engine.dispose()
