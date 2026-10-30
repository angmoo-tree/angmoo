from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
import pytest
from sqlalchemy import select
from runtime.test_activity_relationship_validation import relation_case, _lane, _new_state
from app.contracts.relationship_currentness import EFFECT_PROGRESS_KEY, EFFECT_PROGRESS_REVISION, PREVIOUS_CURRENTNESS, CURRENTNESS_REVISION
from app.runtime.social.planned_actions import _execute_planned_action
from app.runtime.autonomous_activity.relationship_progress import PRIVATE_KEY, effects
from app.domains.relationships.policies.effect_progress import RelationshipEffect, proves
from app.domains.relationships.contracts.social_context import RelationshipValidationReference
from model_fixture_support import models


def state_for(case, policy=PREVIOUS_CURRENTNESS):
    # Exact version chains remain meaningful for already saved older policies.
    lane, state = _lane(case), _new_state(case, policy=policy)
    lane.lane = "inbox"
    state["identity"][EFFECT_PROGRESS_KEY] = EFFECT_PROGRESS_REVISION
    state["relationship_validation_receipts"]["post-target"]["binding"]["lane"] = "inbox"
    original = case.db.get(models.Post, "post-target")
    clone = models.Post(**{column.key: getattr(original, column.key) for column in models.Post.__table__.columns if column.key != "id"}, id="post-next")
    case.db.add(clone); case.db.commit()
    candidate = deepcopy(state["candidates"][0]); candidate["target_id"] = "post-next"
    state["candidates"].append(candidate)
    receipt = deepcopy(state["relationship_validation_receipts"]["post-target"])
    receipt["binding"]["target_id"] = "post-next"
    state["relationship_validation_receipts"]["post-next"] = receipt
    state["selections"].append({"target_id":"post-next"})
    state["decision"] = {"decisions": [{"target_id":target, "action":"like", "brief":"Acknowledge"} for target in ("post-target", "post-next")]}
    state["drafts"] = []
    state["lane_data"] = {target:{"post_id":target} for target in ("post-target", "post-next")}
    from app.runtime.autonomous_activity.initial_input import seal
    state.update(seal(state, {}))
    return lane, state


def test_initial_policy_keeps_content_and_reuses_effect_without_version_proof(relation_case):
    case = relation_case
    lane, state = state_for(case, CURRENTNESS_REVISION)
    first = execute(lane, state, "post-target", 0)
    assert first["status"] == "succeeded"
    assert PRIVATE_KEY not in lane.completed_action(state, "post-target").result
    case.rows[0].version += 1
    case.rows[0].perception = "New perception for the next decision"
    case.db.commit()
    assert execute(lane, state, "post-next", 1)["status"] == "succeeded"
    assert execute(lane, state, "post-target", 0)["status"] == "reused"
    assert len(list(case.db.scalars(select(models.PostLike)))) == 2


def execute(lane, state, target, index):
    return _execute_planned_action(lane.ctx, action={"action_type":"like", "post_id":target, "brief":"Acknowledge"},
        scope="inbox", index=index, writing={}, relationship_validator=lane.effect_relationship_validator(state, target))


def test_own_success_allows_next_action_and_restart_reuses_canonical_proof(relation_case):
    case = relation_case
    lane, state = state_for(case)
    frozen = deepcopy(state["relationship_validation_receipts"])
    first = execute(lane, state, "post-target", 0)
    assert first["status"] == "succeeded"
    proof = lane.completed_action(state, "post-target").result[PRIVATE_KEY]
    assert proof["changes"]
    assert PRIVATE_KEY not in str(first)
    # New adapter, same checkpoint; proof came from committed execution, not RAM.
    restarted = _lane(case); restarted.lane = "inbox"
    restarted.validate_relationship_candidates(state, [state["candidates"][1]])
    assert execute(restarted, state, "post-next", 1)["status"] == "succeeded"
    assert state["relationship_validation_receipts"] == frozen
    assert len(list(case.db.scalars(select(models.PostLike)))) == 2


@pytest.mark.parametrize("change", ["external", "view", "facts", "policy", "decision", "event"])
def test_external_or_unproven_changes_still_fail_and_keep_prior_success(relation_case, change):
    case = relation_case
    lane, state = state_for(case)
    assert execute(lane, state, "post-target", 0)["status"] == "succeeded"
    if change == "external": case.rows[0].version += 1
    elif change == "view": case.rows[0].view_version += 1
    elif change == "facts": case.rows[0].perception = "Changed outside this decision"
    elif change == "policy": state["identity"].pop(EFFECT_PROGRESS_KEY)
    elif change == "decision": state["drafts"] = [{"body":"another decision"}]
    else:
        row = lane.completed_action(state, "post-target")
        case.db.get(models.SocialEvent, row.social_event_id).invalidated_at = datetime.now(UTC)
    case.db.commit()
    with pytest.raises(ValueError):
        lane.validate_relationship_candidate(state, state["candidates"][1])
    assert lane.completed_action(state, "post-target").status == "succeeded"
    assert len(list(case.db.scalars(select(models.PostLike)))) == 1


def test_exact_chain_rejects_aba_and_gaps_even_when_last_values_match():
    base = RelationshipValidationReference("relation", "target", 1, 1, "a"*64)
    own = replace(base, relationship_version=2, facts_digest="b"*64)
    later = replace(base, relationship_version=3, facts_digest="c"*64)
    assert proves(base, later, [RelationshipEffect(base,own), RelationshipEffect(own,later)])
    assert not proves(base, later, [RelationshipEffect(base,own), RelationshipEffect(replace(own,view_version=2),later)])
    assert not proves(base, base, [RelationshipEffect(base,own)])


def test_effect_and_private_proof_rollback_together(relation_case, monkeypatch):
    from app.runtime.autonomous_activity import relationship_progress
    case = relation_case
    lane, state = state_for(case)
    original = relationship_progress.record
    def fail_after_proof(*args):
        original(*args)
        raise RuntimeError("synthetic failure after effect proof")
    monkeypatch.setattr(relationship_progress, "record", fail_after_proof)
    assert execute(lane, state, "post-target", 0)["status"] == "failed"
    assert list(case.db.scalars(select(models.PostLike))) == []
    for row in case.db.scalars(select(models.AgentPublicActionExecution)):
        assert row.status != "succeeded" and PRIVATE_KEY not in (row.result or {})
    case.db.expire_all()
    assert case.rows[0].version == 1


def test_proof_lookup_is_bounded_and_private_result_is_not_public(relation_case):
    from sqlalchemy import event
    from app.contracts.public_activity_result import public_execution_result
    case = relation_case
    lane, state = state_for(case)
    assert execute(lane, state, "post-target", 0)["status"] == "succeeded"
    statements = []
    def count(_conn, _cursor, sql, _parameters, _context, _many):
        statements.append(sql)
    event.listen(case.engine, "before_cursor_execute", count)
    try:
        assert effects(lane, state, "post-next")
    finally:
        event.remove(case.engine, "before_cursor_execute", count)
    assert len(statements) <= 5  # execution/binding/event only, independent of DB size
    result = lane.completed_action(state, "post-target").result
    assert PRIVATE_KEY in result
    assert PRIVATE_KEY not in public_execution_result(result)
    print(f"relationship_proof_lookup statements={len(statements)} prior_actions=1 max_actions=3 max_references=36")
