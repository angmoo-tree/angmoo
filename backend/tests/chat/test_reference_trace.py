"""Reference diagnostics must explain rejection without changing its contract."""
import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import insert, select

from app.domains.chat.contracts.reference_observation import _active, reference_attempt
from app.domains.chat.contracts.retrieval_router_provider import RetrievalRouterRequest
from app.domains.chat.contracts.supervisor_selection import SelectionArgumentOptions, SelectionToolCall, parse_control_selection
from app.integrations import direct_llm
from app.integrations.llm.supervisor_selection import DirectLlmSupervisorSelectionProvider
from app.providers.contracts import ProviderToolCall
from test_decision_diagnostics import material, recording
from test_p8_l_k_retrieval_router import _payload
from test_p8_l_p_evidence_response_streaming import response_session, _request
from app.domains.chat.contracts.retrieval_intent import RetrievalRoute


def arguments():
    payload = _payload("GRAPH")
    return {k: payload[k] for k in ("intent", "entities", "relationship", "aggregation", "time_scope")}


def execute(monkeypatch, args, detailed, *, phase="first", tools=("GRAPH",)):
    requests = []
    async def generate(**kwargs):
        requests.append({k: kwargs[k] for k in ("system_prompt", "user_prompt", "tools", "max_output_tokens", "thinking_level")})
        kwargs["tracker"].next_provider_call_order()
        return SimpleNamespace(text="", finish_reason="STOP", usage={},
            tool_calls=tuple(ProviderToolCall(name, deepcopy(args), f"fixture-{i}") for i, name in enumerate(tools)))
    monkeypatch.setattr(direct_llm, "generate_text", generate)
    with recording(detailed) as observation:
        provider = DirectLlmSupervisorSelectionProvider(material(), native_controls=True, code_coordination=True)
        try:
            value = asyncio.run(provider.route(RetrievalRouterRequest(user_message="canary-question", repair_diagnostic="entity_ref_invalid" if phase == "repair" else None)))
            outcome = value.intent.payload()
        except ValueError as error:
            outcome = (type(error).__name__, str(error))
    assert _active.get() is None
    return observation, outcome, requests


@pytest.mark.parametrize("ref,reason,feature", [
    ("bad_ref", "ref_format_invalid", "has_underscore"),
    ("Upper", "ref_format_invalid", "has_uppercase"),
    ("7start", "ref_format_invalid", None),
    ("인물", "ref_format_invalid", "has_non_ascii"),
    ("bad.ref", "ref_format_invalid", "has_other"),
    ("two words", "ref_format_invalid", "has_space"),
    ("a" * 65, "length_exceeded", None),
    ("   ", "empty_after_normalization", None),
    (None, "invalid_type", None), (32, "invalid_type", None),
])
def test_exact_rejected_entity_and_shape_preserve_provider_contract(monkeypatch, ref, reason, feature):
    args = arguments()
    args["entities"].insert(0, {"ref": "good", "mention": "canary-person", "role": "counterpart"})
    args["entities"][1]["ref"] = ref
    off, off_result, off_calls = execute(monkeypatch, args, False)
    on, on_result, on_calls = execute(monkeypatch, args, True)
    assert off_result == on_result and off_calls == on_calls
    assert not off.details and not off.trace_aliases
    row = next(r for r in on.details if r["event"] == "reference_failure")
    assert row["field_path"] == "entities.ref" and row["entity_index"] == 1 and row["call"] == 1
    assert row["failure_reason"] == reason
    if feature:
        assert row[feature] == "yes"
    assert "canary-" not in json.dumps(on.details)
    assert not any(r["event"].startswith("graph_") for r in on.details)


@pytest.mark.parametrize("ref", ["a", "a" * 64, "  entity-1  "])
def test_valid_and_normalized_refs_do_not_become_failures(monkeypatch, ref):
    args = arguments()
    args["entities"][0]["ref"] = ref
    args["relationship"]["to"] = ref.strip()
    on, result, _ = execute(monkeypatch, args, True)
    assert isinstance(result, dict)
    assert not any(r["event"] == "reference_failure" for r in on.details)
    assert {r["input_stage"] for r in on.details if r["event"] == "reference_inputs"} == {"received_arguments", "normalized_arguments", "validated_intent"}


@pytest.mark.parametrize("kind", ["self_builtin", "self_alias", "unbound", "missing", "builtin_entity"])
def test_relationship_failure_distinctions(monkeypatch, kind):
    args = arguments()
    if kind == "self_builtin":
        args["relationship"]["to"] = args["relationship"]["from"]
    elif kind == "self_alias":
        args["relationship"]["from"] = args["relationship"]["to"]
    elif kind == "unbound":
        args["relationship"]["to"] = "not-declared"
    elif kind == "missing":
        del args["entities"][0]["ref"]
    else:
        args["entities"][0]["ref"] = "responding_character"
    on, _, _ = execute(monkeypatch, args, True, phase="repair")
    row = next(r for r in on.details if r["event"] == "reference_failure")
    assert row["phase"] == "repair"
    if kind.startswith("self"):
        assert row["same_endpoint"] == "yes" and row["ref_alias"] == row["to_ref"]
    elif kind == "unbound":
        assert row["to_resolution"] == "undeclared" and row["to_ref"].startswith("ref-")
    elif kind == "missing":
        assert row["failure_reason"] == "missing"
    else:
        assert row["failure_reason"] == "ref_format_invalid" and row["has_underscore"] == "yes"


def test_both_shared_validation_has_explicit_call_provenance(monkeypatch):
    args = arguments()
    on, result, _ = execute(monkeypatch, args, True, tools=("CANONICAL", "GRAPH"))
    assert result["route"] == "BOTH"
    rows = [r for r in on.details if r["event"] == "reference_inputs"]
    assert {(r["call"], r["input_stage"]) for r in rows} >= {(1, "received_arguments"), (2, "received_arguments"), (1, "validated_intent")}
    assert on.detail_omitted == 0


def test_reference_scope_cleanup_and_bounded_long_invalid_input():
    args = arguments()
    args["entities"][0]["ref"] = "X" * 10000
    with recording(True) as observation:
        with pytest.raises(ValueError), reference_attempt("first"):
            parse_control_selection("", (SelectionToolCall("id", "GRAPH", json.dumps(args)),), options=SelectionArgumentOptions(True, False))
    assert _active.get() is None
    row = next(r for r in observation.details if r["event"] == "reference_failure")
    assert row["features_complete"] == "no" and row["ref_alias"] == "unresolved"
    assert len(json.dumps(observation.details)) < 65536


def test_history_contains_failed_and_no_evidence_with_stable_pages(response_session):
    from app.domains.chat.models import ChatResponseRequest
    from app.domains.chat.repository.diagnostic_requests import list_requests
    original = _request(response_session, RetrievalRoute.GRAPH)
    response_session.commit()
    row = response_session.get(ChatResponseRequest, original.request_id)
    template = {col.name: getattr(row, col.name) for col in ChatResponseRequest.__table__.columns}
    created = datetime.now(UTC) + timedelta(days=1)
    states = ["failed", "cancelled", "accepted", "committed"]
    values = [{**template, "request_id": f"history-{i:03}", "response_slot_id": f"history-{i}",
               "idempotency_key": f"history-{i}", "created_at": created, "state": states[i % 4]} for i in range(65)]
    for value in values:
        if value["state"] != "accepted":
            value["terminal_at"] = created
            value["terminal_reason"] = {"failed": "provider_failure", "cancelled": "user_cancelled", "committed": "committed"}[value["state"]]
            if value["state"] == "committed":
                value["committed_assistant_message_id"] = row.user_message_id
    response_session.execute(insert(ChatResponseRequest), values)
    response_session.commit()
    before = list(response_session.scalars(select(ChatResponseRequest.request_id)))
    result = list_requests(response_session, row.thread_id)
    all_items = result["items"][:]
    assert len(all_items) == 30 and {r["state"] for r in all_items} == set(states)
    while result["next_cursor"]:
        result = list_requests(response_session, row.thread_id, cursor=result["next_cursor"])
        all_items.extend(result["items"])
    assert len(all_items) == 66 and len({r["request_id"] for r in all_items}) == 66
    assert all_items[0]["request_id"] == "history-064"
    assert set(all_items[0]) == {"request_id", "created_at", "state", "user_message_id", "attempt_number", "retry_of_request_id"}
    with pytest.raises(ValueError):
        list_requests(response_session, "other-thread", cursor=row.request_id)
    with pytest.raises(ValueError):
        list_requests(response_session, row.thread_id, limit=101)
    assert before == list(response_session.scalars(select(ChatResponseRequest.request_id)))


def test_history_http_uses_owner_scope_and_validates_cursor():
    from test_p8_l_d_world_chat_api import _fixture, _seed, FRONTEND_HEADERS
    from app.domains.chat.router.retrieval_diagnostics import router
    client, engine, principal = _fixture()
    client.app.include_router(router, prefix="/api/v1")
    owner, outsider, responding = _seed(engine, principal)
    thread = client.post("/api/v1/worlds/world-a/chat/threads", headers=FRONTEND_HEADERS,
                         json={"responding_world_character_id": responding}).json()["thread"]["id"]
    url = f"/api/v1/worlds/world-a/chat/threads/{thread}/diagnostics/requests"
    result = client.get(url)
    assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
    assert result.json()["items"] == []
    assert client.get(url + "?limit=101").status_code == 422
    assert client.get(url + "?cursor=not-found").status_code == 422
    principal["user"] = outsider
    assert client.get(url).status_code == 403
    principal["user"] = owner
    assert client.get(url.replace("world-a", "world-b")).status_code == 404
    principal["user"] = None
    assert client.get(url).status_code == 401
    client.close()
    engine.dispose()


def test_resolution_provenance_uses_existing_binding_and_query_count():
    from app.domains.chat.service import RetrievalRoutingService
    from app.domains.chat.contracts import RetrievalEntityResolution, parse_retrieval_intent_payload
    from test_p8_l_k_retrieval_router import _FakePolicy, _FakeRouter, _candidate, _command
    outputs = []
    for detailed in (False, True):
        intent = parse_retrieval_intent_payload(_payload("GRAPH"))
        policy = _FakePolicy((RetrievalEntityResolution("entity-1", (_candidate("canary-identity"),)),))
        service = RetrievalRoutingService(router=_FakeRouter(intent), policy=policy)
        now = datetime.now(UTC)
        with recording(detailed) as observation:
            result = asyncio.run(service.route(_command(), now=now, deadline_at=now + timedelta(seconds=30)))
        outputs.append((result.resolved.entity_bindings, result.resolved.relationship_to_world_character_id, policy.load_calls))
        if detailed:
            rows = [r for r in observation.details if r["event"] == "resolved_references"]
            assert [r["input_stage"] for r in rows] == ["entity_resolution", "resolved_binding"]
            assert rows[1]["entity_1_identity"] == rows[1]["upstream_to"]
            assert rows[1]["upstream_from"] == "responding_character"
            assert rows[0]["entity_1_identity"] == "not_evaluated"
            assert "canary-identity" not in json.dumps(rows)
    assert outputs[0] == outputs[1]
