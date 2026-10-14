from datetime import UTC, datetime
from sqlalchemy.orm import Session
import pytest

from runtime.test_activity_settlement_sqlite import _fixture
from app.domains.world_characters.activity_models import CharacterActivityState
from app.domains.world_characters.service.activity_state import settle_state, confirmed_settlement


@pytest.mark.parametrize("mutation", [None, "expected_version", "source_keys", "activity_id", "actor_id"])
def test_exact_307_to_308_receipt_is_required_for_state_replay(tmp_path, mutation):
    engine, _, (identity,) = _fixture(tmp_path)
    world_id, actor_id = identity[:2]
    now = datetime.now(UTC)
    keys = ["post:frozen-source-revision"]
    with Session(engine) as db:
        db.add(CharacterActivityState(world_id=world_id, world_character_id=actor_id, version=307,
            mood="calm", mood_intensity=1, state_note="Quiet"))
        db.commit()
        assert settle_state(db, world_id=world_id, actor_id=actor_id, activity_id="same-activity", decision_key="same-decision",
            expected_version=307, proposal=None, judged_at=now, source_keys=keys, valid_source_keys=set(keys)) == "kept"
        db.commit()
        arguments = dict(world_id=world_id, actor_id=actor_id, activity_id="same-activity", decision_key="same-decision",
            expected_version=307, judged_at=now, source_keys=keys)
        if mutation:
            arguments[mutation] = 306 if mutation == "expected_version" else ["different-source"] if mutation == "source_keys" else "other"
            with pytest.raises(ValueError, match="binding_invalid"):
                confirmed_settlement(db, **arguments)
        else:
            assert confirmed_settlement(db, **arguments).resulting_version == 308
            assert settle_state(db, proposal=None, valid_source_keys=set(keys), **arguments) == "kept"
            db.commit()
            assert db.get(CharacterActivityState, actor_id).version == 308
    engine.dispose()
