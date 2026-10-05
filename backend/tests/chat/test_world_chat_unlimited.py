"""No credentials or generation: World tuple reuse and the explicit unlimited read contract."""
from datetime import UTC, datetime
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from model_fixture_support import models
from chat.test_p8_l_d_world_chat_identity import _create_tables, _user, _installation, _character, _seed_world, _world_character
from chat_service_support import messages as world_chat
from app.domains.chat import schemas


def test_twenty_world_threads_create_and_reuse_without_a_cross_world_quota(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'world-chat.db'}")
    _create_tables(engine)
    with Session(engine) as db:
        owner, other = _user("owner"), _user("other")
        requester, responding = _character("requester", owner.id), _character("responding", other.id)
        db.add_all([owner, other, _installation(owner.id), requester, responding]); db.flush()
        _actor, first = _seed_world(db, owner=owner, responder_owner=other, world_id="world-unlimited",
            requester_character=requester, responding_character=responding, suffix="initial")
        targets = [first.id]
        for index in range(19):
            character = _character(f"responder-{index}", other.id); db.add(character); db.flush()
            target = _world_character("world-unlimited", character.id, membership_id="membership-world-unlimited-responder", suffix=f"extra-{index}")
            db.add(target); targets.append(target.id)
            db.flush()
            from app.runtime.world_characters.creation_configuration import initialize_created_world_character
            initialize_created_world_character(db, character=character, world_character=target)
        db.commit()
        created = []
        for target in targets:
            result = world_chat.create_or_get_world_thread(db, owner, "world-unlimited", schemas.WorldChatThreadCreate(responding_world_character_id=target))
            assert result.outcome == "created"; created.append(result.thread.id)
        replay = world_chat.create_or_get_world_thread(db, owner, "world-unlimited", schemas.WorldChatThreadCreate(responding_world_character_id=targets[5]))
        assert replay.outcome == "reused" and replay.thread.id == created[5]
        read = world_chat.list_world_threads(db, owner, "world-unlimited")
        assert read.max_threads is None and len(read.items) == 20
        assert read.model_dump()["max_threads"] is None
        assert db.scalar(select(func.count(models.MessageThread.id))) == 20
    with Session(engine) as fresh:
        assert world_chat.list_world_threads(fresh, fresh.get(models.User, "owner"), "world-unlimited").max_threads is None
    engine.dispose()
