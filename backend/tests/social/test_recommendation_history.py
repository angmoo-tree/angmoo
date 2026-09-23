"""Delivery history is a read model, never a reconstruction from legacy observations."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, select

from social.test_recommendation_topics import scope, post
from app.domains.social.models.feed import WorldCharacterFeedObservation
from app.domains.social.models.topics import RecommendationDelivery
from app.runtime.social.topic_preparation import read_topics

NOW = datetime(2026, 9, 20, tzinfo=UTC)


def observation(db, world, wc, row, cycle="cycle", **values):
    result = WorldCharacterFeedObservation(
        id=f"obs-{row.id}", world_id=world.id, observer_world_character_id=wc.id,
        post_id=row.id, status="observed", claim_token="test", cycle_key=cycle,
        run_id="run", lease_expires_at=NOW, claimed_at=NOW, observed_at=NOW,
        post_created_at=NOW, **values,
    )
    db.add(result)
    return result


def delivery(db, world, wc, ids, cycle="cycle", state="delivered", **values):
    result = RecommendationDelivery(id=f"delivery-{cycle}", world_id=world.id,
        world_character_id=wc.id, cycle_key=cycle, state=state, post_ids=ids,
        updated_at=NOW, **values)
    db.add(result)
    return result


def read(scope):
    db, world, character, wc = scope
    return read_topics(db, world_id=world.id, owner_id=character.owner_id, world_character_id=wc.id)


def test_legacy_observation_is_not_delivery_history(scope):
    db, world, character, wc = scope
    old = post(db, world, character, wc, "legacy")
    observation(db, world, wc, old)
    db.commit()
    response = read(scope)
    assert response["recent_feed"] == []
    assert response["recent_deliveries"] == []


def test_only_delivered_ids_and_same_cycle_results_are_used(scope):
    db, world, character, wc = scope
    old = post(db, world, character, wc, "old")
    new = post(db, world, character, wc, "new")
    observation(db, world, wc, old, "old-cycle", selected_action="comment", decision_outcome="action_selected")
    observation(db, world, wc, new, "wrong-cycle", selected_action="comment", decision_outcome="action_selected")
    delivery(db, world, wc, [new.id], trace={new.id: {"lane": "latest", "sources": ["latest"]}, old.id: {"lane": "interest"}})
    db.commit()
    response = read(scope)
    assert [p["post_id"] for p in response["recent_feed"]] == [new.id]
    item = response["recent_deliveries"][0]["posts"][0]
    assert item["lane"] == "latest" and item["result_state"] == "unrecorded"


@pytest.mark.parametrize("state", ["prepared", "dispatched", "uncertain"])
def test_non_delivered_states_never_appear(scope, state):
    db, world, character, wc = scope
    row = post(db, world, character, wc)
    observation(db, world, wc, row)
    delivery(db, world, wc, [row.id], state=state)
    db.commit()
    assert read(scope)["recent_feed"] == []


def execution(db, character, wc, obs, status="succeeded", **values):
    from app.domains.routines.models.resident import AgentRun, AgentPublicActionExecution
    from app.domains.social.service.feed_cycle_values import execution_signature_values
    run_id = values.pop("run_id", obs.run_id)
    db.add(AgentRun(id=run_id, user_id=character.owner_id, character_id=character.id,
                    agent_id="fixture", session_key="fixture"))
    db.flush()
    data = dict(run_id=run_id, character_id=character.id, world_id=wc.world_id,
                actor_world_character_id=wc.id, feed_observation_id=obs.id,
                target_post_id=obs.post_id, action_type=obs.selected_action,
                scope="world_keyword_feed", interaction_intent=obs.interaction_intent,
                signature=execution_signature_values(world_character_id=wc.id, world_id=wc.world_id,
                    action=obs.selected_action, post_id=obs.post_id,
                    interaction_intent=obs.interaction_intent, cycle_key=obs.cycle_key), status=status)
    data.update(values)
    row = AgentPublicActionExecution(**data)
    db.add(row); db.flush()
    obs.public_action_execution_id = row.id
    return row


@pytest.mark.parametrize("state,expected", [(None, "selected"), ("pending", "pending"),
    ("succeeded", "succeeded"), ("failed", "failed"), ("unknown", "unrecorded")])
def test_selection_is_not_success(scope, state, expected):
    db, world, character, wc = scope
    row = post(db, world, character, wc)
    obs = observation(db, world, wc, row, decision_outcome="action_selected", selected_action="comment")
    db.flush()
    if state:
        execution(db, character, wc, obs, state)
    delivery(db, world, wc, [row.id]); db.commit()
    item = read(scope)["recent_deliveries"][0]["posts"][0]
    assert item["result_state"] == expected


@pytest.mark.parametrize("field,value", [("scope", "other"), ("action_type", "like"),
    ("target_post_id", None), ("actor_world_character_id", None), ("world_id", None),
    ("feed_observation_id", None), ("character_id", "other"), ("interaction_intent", "ordinary_comment")])
def test_execution_scope_mismatch_is_unknown(scope, field, value):
    db, world, character, wc = scope
    row = post(db, world, character, wc)
    obs = observation(db, world, wc, row, decision_outcome="action_selected", selected_action="comment")
    db.flush()
    if field == "character_id":
        from social.test_world_feed_search import _add_world_character
        _, other, _ = _add_world_character(db, world=world, suffix="other")
        value = other.id
    execution(db, character, wc, obs, **{field: value})
    delivery(db, world, wc, [row.id]); db.commit()
    assert read(scope)["recent_deliveries"][0]["posts"][0]["result_state"] == "unrecorded"


@pytest.mark.parametrize("valid", [True, False])
def test_reused_success_requires_same_cycle_signature(scope, valid):
    db, world, character, wc = scope
    row = post(db, world, character, wc)
    obs = observation(db, world, wc, row, decision_outcome="action_selected", selected_action="comment")
    db.flush()
    result = execution(db, character, wc, obs, run_id="old-run")
    if not valid:
        result.signature = "other-cycle"
    delivery(db, world, wc, [row.id]); db.commit()
    assert read(scope)["recent_deliveries"][0]["posts"][0]["result_state"] == ("succeeded" if valid else "unrecorded")


@pytest.mark.parametrize("outcome,reason,expected", [("no_action", "model_abstained", "no_action"),
    ("no_action", "writer_invalid", "not_performed"), ("no_action", None, "unrecorded"),
    ("not_selected", None, "not_selected"), (None, None, "unrecorded")])
def test_result_without_action_is_not_invented(scope, outcome, reason, expected):
    db, world, character, wc = scope
    row = post(db, world, character, wc)
    observation(db, world, wc, row, decision_outcome=outcome, reason_code=reason)
    delivery(db, world, wc, [row.id], trace={row.id: {"lane": [], "sources": ["latest", "bad", "latest"]}})
    db.commit()
    item = read(scope)["recent_deliveries"][0]["posts"][0]
    assert item["result_state"] == expected
    assert item["lane"] is None and item["sources"] == ["latest"]


@pytest.mark.parametrize("hidden", ["deleted_at", "report_hidden_at", "visibility", "block", "membership"])
def test_current_visibility_hides_details_but_keeps_delivery(scope, hidden):
    from social.test_world_feed_search import _add_world_character
    from app.domains.social.models.feed import WorldCharacterBlock
    from app.domains.worlds.models import WorldMembership
    db, world, character, wc = scope
    _, author, author_wc = _add_world_character(db, world=world, suffix="author")
    row = post(db, world, author, author_wc)
    delivery(db, world, wc, [row.id])
    if hidden == "block":
        db.add(WorldCharacterBlock(id="block", world_id=world.id,
            blocker_world_character_id=author_wc.id, blocked_world_character_id=wc.id))
    elif hidden == "membership":
        db.get(WorldMembership, author_wc.membership_id).status = "left"
    else:
        setattr(row, hidden, "private" if hidden == "visibility" else NOW)
    db.commit()
    history = read(scope)["recent_deliveries"]
    assert len(history) == 1 and history[0]["posts"] == []
    assert history[0]["unavailable_post_count"] == 1 and history[0]["recorded_post_count"] == 1


def test_bounded_batches_order_and_read_only(scope):
    from app.runtime.social.recommendation_history import read_delivery_history
    from time import perf_counter
    db, world, character, wc = scope
    rows = [post(db, world, character, wc, f"post-{i:03}") for i in range(105)]
    for index, row in enumerate(rows):
        observation(db, world, wc, row, cycle=f"cycle-{index // 20}")
    for index in range(6):
        delivery(db, world, wc, [p.id for p in rows[index * 20:(index + 1) * 20]], cycle=f"cycle-{index}")
    db.commit()
    statements = []
    def collect(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(db.bind, "before_cursor_execute", collect)
    try:
        started = perf_counter()
        history = read_delivery_history(db, world_id=world.id, world_character_id=wc.id)
        elapsed = (perf_counter() - started) * 1000
    finally:
        event.remove(db.bind, "before_cursor_execute", collect)
    assert len(history) == 5 and history[0]["delivery_id"] == "delivery-cycle-5"
    assert len(history[1]["posts"]) == 20
    assert [p["post_id"] for p in history[1]["posts"]] == [p.id for p in rows[80:100]]
    # Session expiration may add two fixture attribute reloads before the reader.
    assert len(statements) <= 6 and all(s.lstrip().upper().startswith("SELECT") for s in statements)
    assert not db.dirty and not db.new and not db.deleted
    print(f"history: {len(statements)} SELECTs, {elapsed:.2f} ms, 5 deliveries / 85 visible posts")


@pytest.mark.parametrize("ids,count", [(None, None), (["new", "new", 123], None), (["new"], 1), (["new"] * 25, None)])
def test_malformed_receipt_is_bounded_and_never_fake_zero(scope, ids, count):
    db, world, character, wc = scope
    row = post(db, world, character, wc)
    receipt = delivery(db, world, wc, [], trace=[])
    db.flush()
    receipt.post_ids = ids
    db.commit()
    group = read(scope)["recent_deliveries"][0]
    assert group["recorded_post_count"] == count
    assert group["is_partial"] == (count is None)
    assert len(group["posts"]) <= 1


def test_world_character_and_owner_isolation(scope):
    from social.test_world_feed_search import _add_world_character, _world, _user
    from app.domains.social.contracts.recommendation import TopicPreparationError
    db, world, character, wc = scope
    _, author, other_wc = _add_world_character(db, world=world, suffix="other")
    row = post(db, world, author, other_wc)
    delivery(db, world, other_wc, [row.id])
    owner = _user("second-world-owner"); db.add(owner); db.flush()
    other_world = _world(owner, "b"); db.add(other_world); db.flush()
    db.commit()
    assert read(scope)["recent_deliveries"] == []
    with pytest.raises(TopicPreparationError):
        read_topics(db, world_id=world.id, world_character_id=other_wc.id, owner_id=character.owner_id)
    with pytest.raises(TopicPreparationError):
        read_topics(db, world_id=other_world.id, world_character_id=wc.id, owner_id=character.owner_id)
