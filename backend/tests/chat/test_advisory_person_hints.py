"""Native v3 core execution is independent of optional person interpretation."""
import asyncio
import json
from types import SimpleNamespace
import pytest
from chat.test_named_selection_lifecycle import admission, EmptyHybrid
from chat.test_p8_l_p_evidence_response_streaming import response_session
from chat import test_p8_l_p_evidence_response_streaming as f
from chat.test_named_supervisor_selection import arguments
from app.config import Settings
from app.domains.chat.contracts.person_hints import normalize_person_hints
from app.domains.chat.contracts.supervisor_selection import (
    SelectionArgumentOptions, SelectionToolCall, parse_control_selection, model_arguments_schema,
    ADVISORY_SELECTION_PROTOCOL,
)
from app.providers.contracts import ProviderToolCall
from app.runtime.chat.message_composition import generation_service


def options():
    return SelectionArgumentOptions(code_coordination=True, social_context_mode=True,
        hybrid_recall=True, advisory_hints=True)


def core(control="USE_CONTEXT", hints=None):
    args = arguments()
    args.pop("relationship")
    args["entities"] = hints
    if control != "CANONICAL":
        args.pop("search_text")
        args["intent"] = "current_context"
    if control == "REQUEST_CLARIFICATION":
        args.update(intent="clarification_required", clarification_slot="counterpart")
    return args


@pytest.mark.parametrize("hints", [None, "bad", {}, [None, 5, {"mention": ""}],
    [{"mention": "rad", "role": "invalid"}], [{"mention": "진구", "role": []}],
    [{"mention": "X"*161}], [{"mention": "Bram\n", "role": "actor"}]])
@pytest.mark.parametrize("control", ["CANONICAL", "USE_CONTEXT", "REQUEST_CLARIFICATION"])
def test_optional_hints_never_reject_valid_core(hints, control):
    args = core(control, hints=hints)
    call = SelectionToolCall("call", control, json.dumps(args))
    envelope = parse_control_selection("", (call,), options=options())
    assert envelope.version == "retrieval-intent.v3"
    assert envelope.relationship is None and envelope.entities == ()
    assert "relationship" not in model_arguments_schema(options())["properties"]
    assert "entities" not in model_arguments_schema(options())["required"]


@pytest.mark.parametrize("change", [lambda args: args.update(search_text=""),
    lambda args: args.update(search_text=42), lambda args: args.update(sql="SELECT * FROM secret"),
    lambda args: args.update(intent="unknown"), lambda args: args.update(world_character_id="untrusted-id")])
def test_invalid_core_still_rejects_even_when_all_hints_are_usable(change):
    from app.domains.chat.contracts.retrieval_intent import RetrievalContractError
    args = core("CANONICAL", hints=[{"mention": "Bram", "role": "actor"}])
    change(args)
    with pytest.raises(RetrievalContractError):
        parse_control_selection("", (SelectionToolCall("call", "CANONICAL", json.dumps(args)),), options=options())


def test_bounds_duplicate_roles_and_fingerprint():
    raw = [{"mention": "Red"}, {"mention": "Red", "role": "actor"}]
    normalized = normalize_person_hints(raw)
    assert len(normalized.hints) == 1 and normalized.hints[0].role == "actor"
    assert raw[0] == {"mention": "Red"}
    rows = normalize_person_hints([{"mention": str(i), "role": "subject"} for i in range(100)])
    assert len(rows.hints) == 4 and rows.reviewed == 32 and rows.excluded == 96
    assert normalize_person_hints(None).input_digest != normalize_person_hints([]).input_digest


@pytest.mark.parametrize("hints", [None, "bad", [{"mention": "rad", "role": 42}],
    [{"mention": "진구", "role": "subject"}], [{"mention": "Bram", "role": "actor", "ref": "wrong"}]])
@pytest.mark.parametrize("control", ["USE_CONTEXT", "CANONICAL"])
def test_real_admission_provider_commit_without_hint_repair(response_session, monkeypatch, hints, control):
    from app.integrations import direct_llm
    db = response_session
    owner, accepted, _ = admission(db, monkeypatch, memory=True, protocol=None)
    calls = []
    async def provider(**kwargs):
        assert not db.in_transaction()
        calls.append(kwargs)
        kwargs["tracker"].next_call_order()
        kwargs["tracker"].next_provider_call_order()
        if kwargs.get("tools"):
            return SimpleNamespace(text="", parsed=None, usage={}, finish_reason="STOP",
                tool_calls=(ProviderToolCall(control, core(control, hints=hints), "v3-native-call"),))
        payload = json.loads(kwargs["user_prompt"].split("\n", 1)[-1])
        assert payload["recall_interpretation"]["revision"] == "hybrid-admission.v3"
        assert "requested_direction" not in payload["recall_interpretation"]
        answer = {"text": "확인한 내용으로 답한다.", "thought": "근거를 확인한다.",
            "situation_description": "진구가 Bram의 인식을 물었고 Bram은 확인한 내용으로 답했다."}
        return direct_llm.DirectLlmResponse(text=json.dumps(answer, ensure_ascii=False), parsed=answer, usage={}, finish_reason="STOP")
    monkeypatch.setattr(direct_llm, "generate_text", provider)
    asyncio.run(f._collect(generation_service.stream_world_response(db, owner, "p-world", "p-thread",
        accepted.response_request.request_id, memory_recall_service=SimpleNamespace(hybrid_service=EmptyHybrid()),
        runtime_settings=Settings(_env_file=None, CHAT_RECALL_MODE="social_hybrid"))))
    saved = f.SqlAlchemyResponseLifecycleRepository(db).get_request(accepted.response_request.request_id)
    assert saved.state.value == "committed", {k: saved.node_state.get(k) for k in ("failure_class", "router_diagnostic", "crg_diagnostic")}
    assert len(calls) == 2
    assert "from_name" not in calls[0]["system_prompt"] and "entity-1" not in calls[0]["system_prompt"]
    assert "requested_direction" not in calls[1]["system_prompt"]


def test_optional_hint_diagnostics_are_bounded_and_relationship_is_not_applicable():
    from app.contracts.retrieval_observation import Observation, current
    from app.domains.chat.contracts.selection_diagnostics import selection_attempt
    observation = Observation(detailed=True)
    token = current.set(observation)
    try:
        selection_attempt(SimpleNamespace(repair_diagnostic=None, selection_protocol=ADVISORY_SELECTION_PROTOCOL),
            SimpleNamespace(tool_calls=(SimpleNamespace(name="USE_CONTEXT", arguments=core(hints=[
                {"mention": "private-person-name", "role": "bad"}, None])),), finish_reason="STOP", text="", usage={}))
        row = observation.details[-1]
        assert row["hint_state"] == "partial" and row["hints_delivered"] == 1 and row["hints_excluded"] == 1
        assert row["relationship_state"] == "not_applicable"
        assert "private-person-name" not in json.dumps(observation.payload()) + json.dumps(observation.details)
    finally:
        current.reset(token)
