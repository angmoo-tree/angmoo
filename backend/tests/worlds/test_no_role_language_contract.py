from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from app.domains.worlds.contracts import is_canonical_no_specific_role
from app.domains.worlds.exceptions import ReservedWorldRoleConflictError
from app.domains.worlds.service.reserved_roles import ensure_no_specific_role
from app.domains.worlds.service.definition import world_contract_hash
from worlds.test_creator_routes import _app, _payload, _request, _user
from model_fixture_support import models


@pytest.mark.parametrize("name,description,valid", [
    ("No role", "A character with no specific World role.", True),
    ("역할 없음", "별도의 World 역할을 지정하지 않은 캐릭터", True),
    ("No role", "별도의 World 역할을 지정하지 않은 캐릭터", False),
    ("역할 없음", "A character with no specific World role.", False),
    ("No role ", "A character with no specific World role.", False),
    ("역할 없음", "edited", False),
])
def test_only_complete_supported_pairs(name, description, valid):
    role = SimpleNamespace(key="no_specific_role", name=name, description=description,
                           responsibilities=[], allowed_activity_scope=[], autonomous_allowed=True)
    assert is_canonical_no_specific_role(role) is valid
    for field, changed in [("key", "ordinary"), ("responsibilities", ["custom"]),
                           ("allowed_activity_scope", ["custom"]), ("autonomous_allowed", False)]:
        assert not is_canonical_no_specific_role(SimpleNamespace(**{**vars(role), field: changed}))


@pytest.mark.parametrize("legacy", [False, True])
def test_new_english_and_existing_legacy_keep_identity_and_hash(legacy):
    app, engine, principal = _app()
    owner = _user("role-language-owner")
    with Session(engine, expire_on_commit=False) as db:
        db.add(owner); db.commit()
    principal["user"] = owner
    response = _request(app, "POST", "/api/v1/worlds", json=_payload(idempotency_key="role-language"))
    assert response.status_code == 201
    world_id = response.json()["world"]["id"]
    with Session(engine) as db:
        world = db.get(models.World, world_id)
        role = ensure_no_specific_role(db, world_id=world_id)
        assert (role.name, role.description) == ("No role", "A character with no specific World role.")
        if legacy:
            role.name = "역할 없음"
            role.description = "별도의 World 역할을 지정하지 않은 캐릭터"
        db.flush()
        before = (role.id, role.version, role.name, role.description, world_contract_hash(db, world))
        assert ensure_no_specific_role(db, world_id=world_id) is role
        assert (role.id, role.version, role.name, role.description, world_contract_hash(db, world)) == before
        assert not db.dirty
        role.description = "edited"
        db.flush()
        with pytest.raises(ReservedWorldRoleConflictError):
            ensure_no_specific_role(db, world_id=world_id)
        db.rollback()
    engine.dispose()
