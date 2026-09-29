"""A rejected combined reply shares the existing bounded Writer recovery."""
import asyncio
from types import SimpleNamespace

import pytest

from app.contracts.name_binding import NameBindingError, NameBindingSnapshot
from app.runtime.autonomous_activity.combined_lanes import CombinedFeedLane, CombinedInboxLane
from app.runtime.autonomous_activity.combined_provider import CombinedActivityProvider
from app.runtime.autonomous_activity.provider import ActivityProvider


@pytest.mark.parametrize("lane_name,lane_type", [("feed", CombinedFeedLane), ("inbox", CombinedInboxLane)])
@pytest.mark.parametrize("repaired", [True, False])
def test_other_recipient_macro_uses_one_writer_and_never_guesses_owner(monkeypatch, lane_name, lane_type, repaired):
    async def scenario():
        # Identical visible names do not turn another character into the user.
        names = NameBindingSnapshot("owner", "world", "actor", "Sakana", "my-profile", "Seraphina", 2)
        row = SimpleNamespace(result={"name_binding": names.to_dict()})
        ctx = SimpleNamespace(run_id="run", db=SimpleNamespace(get=lambda *args: row))
        reservations, requests = [], []
        def reserve(key):
            assert not reservations
            reservations.append(key)
        async def guard(state):
            return {}
        lane = lane_type.__new__(lane_type)
        lane.ctx, lane.lane, lane.guard = ctx, lane_name, guard
        lane.tracker = SimpleNamespace(observer=None)
        lane.provider = CombinedActivityProvider(ctx, lane.tracker, ledger=SimpleNamespace(reserve=reserve))
        assignment = {"task_id": "task", "target_post_id": "post", "scope": lane_name,
            "action_index": 0, "source": {"target_id": "post", "counterpart_id": "another-character",
                "counterpart_name": "Seraphina", "text": "좋은 하루 보내세요"}}
        state = {"generation_mode": "combined", "assignments": [assignment], "decision_context": {},
            "decision_input_receipt": {}, "decision": {"provisional_draft": {
                "replies": [{"target_id": "post", "body": "{{user}}, 고마워요"}]}}}
        async def call(self, **kwargs):
            requests.append(kwargs)
            assert kwargs["node"] == lane_name.title() + "Writer"
            assert kwargs["payload"]["assignments"] == [assignment]
            feedback = kwargs["payload"]["context"]["writer_feedback"]
            assert feedback["validation_code"] == "name_macro_addressee_ambiguous"
            assert kwargs["json_retry_policy"] is None
            if kwargs["on_input_receipt"]:
                kwargs["on_input_receipt"]({"node": kwargs["node"]})
            return kwargs["validator"]({"replies": [{"task_id": "task",
                "body": "Seraphina, 고마워요" if repaired else "{{user}}, 고마워요"}]})
        monkeypatch.setattr(ActivityProvider, "call", call)
        if repaired:
            result = await lane.write(state)
            assert result["drafts"][0]["body"] == "Seraphina, 고마워요"
            assert result["drafts"][0]["post_id"] == "post"
            assert result["writer_input_receipts"][0]["writer_recovery"] is True
        else:
            with pytest.raises(NameBindingError, match="name_macro_addressee_ambiguous"):
                await lane.write(state)
        assert len(requests) == len(reservations) == 1
        assert lane.provider.repairing is False
        assert state["decision"]["provisional_draft"]["replies"][0]["body"] == "{{user}}, 고마워요"
    asyncio.run(scenario())
