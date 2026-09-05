"""Late read failure keeps the original owner mutation rollback boundary."""
from dataclasses import replace

import pytest
from sqlalchemy.orm import Session

from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.schemas import MemoryPinUpdate
from app.domains.memory.service.management import update_memory_pin
from app.runtime.memory_http import build_memory_workflows
from test_p8_l_q_memory_read_inspector import _fixture, _seed


def test_pin_rolls_back_when_related_profile_read_fails_before_commit():
    client, engine, principal = _fixture()
    seeded = _seed(engine, principal)
    memory_id = str(seeded["memory_id"])
    observed = []

    def unavailable(db, scope):
        row = db.get(MemoryItem, memory_id)
        observed.append((row.pinned_at is not None, row.version, scope))
        raise RuntimeError("profile_read_unavailable")

    scope = MemoryScope("q-owner", "q-world", "q-responding")
    workflows = replace(build_memory_workflows(), character_names=unavailable)
    with Session(engine) as db:
        with pytest.raises(RuntimeError, match="^profile_read_unavailable$"):
            update_memory_pin(
                db=db,
                workflows=workflows,
                scope=scope,
                memory_id=memory_id,
                data=MemoryPinUpdate(
                    schema_version="memory-pin-update.v1",
                    expected_version=1,
                    pinned=True,
                    idempotency_key="pin-profile-read-failure",
                ),
            )
        assert observed == [(True, 2, scope)]
        row = db.get(MemoryItem, memory_id)
        assert row.pinned_at is None
        assert row.version == 1
    client.close()
    engine.dispose()
