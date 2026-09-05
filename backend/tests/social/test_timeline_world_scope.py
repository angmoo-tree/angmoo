from types import SimpleNamespace

import pytest

from app.domains.social.exceptions import PostWorldScopeError
from app.domains.social.service.timeline import _timeline_world_scope


@pytest.mark.parametrize("missing,expected_error,expected_models", [
    ("active", "active_world_required", ["CharacterActiveWorld"]),
    ("character", "target_world_not_active", ["CharacterActiveWorld", "WorldCharacter"]),
    ("membership", "world_membership_not_active", ["CharacterActiveWorld", "WorldCharacter", "WorldMembership"]),
    (None, None, ["CharacterActiveWorld", "WorldCharacter", "WorldMembership"]),
])
def test_timeline_scope_keeps_lookup_order_original_errors_and_same_session(missing, expected_error, expected_models):
    active = SimpleNamespace(world_character_id="wc-author")
    world_character = SimpleNamespace(id="wc-author", character_id="character-author", world_id="world-target", status="active", membership_id="membership-owner")
    membership = SimpleNamespace(world_id="world-target", user_id="owner", status="active")
    objects = {"CharacterActiveWorld": None if missing == "active" else active, "WorldCharacter": None if missing == "character" else world_character, "WorldMembership": None if missing == "membership" else membership}
    calls = []
    read_order = []
    class SessionProbe:
        def get(self, model, identity):
            calls.append((model.__name__, identity))
            read_order.append(model.__name__)
            return objects[model.__name__]
    db = SessionProbe()
    class CharacterProbe:
        id = "character-author"
        @property
        def owner_id(self):
            read_order.append("owner_id")
            return "owner"
    arguments = dict(target=SimpleNamespace(world_id="world-target"), character=CharacterProbe())
    if expected_error:
        with pytest.raises(PostWorldScopeError, match=expected_error):
            _timeline_world_scope(db, **arguments)
    else:
        assert _timeline_world_scope(db, **arguments) == ("world-target", "wc-author")
    assert [model for model, _ in calls] == expected_models
    assert [identity for _, identity in calls] == ["character-author", "wc-author", "membership-owner"][:len(expected_models)]
    assert read_order == expected_models + (["owner_id"] if missing is None else [])
    calls.clear()
    assert _timeline_world_scope(db, target=SimpleNamespace(world_id=None), character=None) == (None, None)
    assert calls == []
