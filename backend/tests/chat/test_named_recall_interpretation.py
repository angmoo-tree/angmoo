"""Versioned model view, immutable role/direction bindings and real adapters."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest

from chat import test_p8_l_p_evidence_response_streaming as f
from chat.test_named_supervisor_selection import arguments, options, call
from chat.test_named_retrieval_resolution import identity
from chat.test_chat_identity_delivery import request as response_request
from chat.test_decision_diagnostics import material, recording
from app.domains.chat.contracts.recall_interpretation import RecallInterpretationContext, NAMED_ADMISSION_REVISION, text_hash
from app.domains.chat.contracts.person_roles import PERSON_ROLES, person_role_description
from app.domains.chat.contracts.recall_mode import ChatRecallMode
from app.domains.chat.contracts.chat_identity_context import ChatIdentityContext, ChatPerson
from app.domains.chat.contracts.retrieval_router_provider import RetrievalRouterRequest, RetrievalRouterOutputError
from app.domains.chat.contracts.supervisor_selection import (
    NAME_SELECTION_PROTOCOL, LEGACY_HYBRID_PROTOCOL, parse_control_selection, SelectionArgumentOptions)
from app.domains.chat.service.evidence_assembly import EvidenceBundleAssembler
from app.integrations.llm.supervisor_selection import DirectLlmSupervisorSelectionProvider, control_selection_tools
from app.integrations.llm.character_response_generator import _system_prompt, _user_payload
from app.integrations.llm.chat_input_presentation import CHAT_PARTICIPANT_INSTRUCTIONS
from app.integrations import direct_llm
from app.providers.contracts import ProviderToolCall


def interpretation(role="actor", *, named=True):
    payload = arguments()
    payload["entities"][0]["role"] = role
    intent = parse_control_selection("", (call(payload),), options=options())
    resolved = f._resolved(intent, "request")
    context = RecallInterpretationContext("request", intent.envelope_hash, resolved.envelope_hash,
        text_hash("Bram은 나를 어떻게 생각해?"), intent.search_text,
        tuple((e.ref, e.mention, "unmatched") for e in intent.entities),
        (intent.relationship.from_ref, intent.relationship.to_ref), None, "not_requested", "ambiguous", None,
        **({"revision": NAMED_ADMISSION_REVISION, "person_roles": tuple(e.role for e in intent.entities)} if named else {}))
    context.assert_routing(intent, resolved)
    evidence = EvidenceBundleAssembler().current_context(request_id="request", request_scope_hash="a"*64)
    return context.freeze(evidence), intent, resolved, evidence


@pytest.mark.parametrize("role", sorted(PERSON_ROLES))
def test_all_roles_reach_actual_crg_view_and_hash(role):
    context, intent, resolved, evidence = interpretation(role)
    item = replace(response_request(raw="Bram은 나를 어떻게 생각해?", participants=identity(), bundle=evidence),
        recall_mode=ChatRecallMode.SOCIAL_HYBRID, recall_interpretation=context)
    view = _user_payload(item)["recall_interpretation"]
    assert view["mentions"][0] == {"mention": "Bram", "role": role, "resolution": "unmatched"}
    assert view["requested_direction"] == {"from_name": "Bram", "to_name": "진구"}
    assert context.manifest()["content_hash"] == context.content_hash
    assert context.content_hash != replace(context, person_roles=("subject" if role != "subject" else "actor", "target")).content_hash
    prompt = _system_prompt(item)
    assert prompt.count(person_role_description()) == prompt.count(CHAT_PARTICIPANT_INSTRUCTIONS) == 1
    assert "Never infer or reveal another Character's private" in prompt
    assert "Do not route, plan, search, call tools" in prompt
    assert "Natural characterful elaboration is allowed" in prompt
    assert "proposed interpretations" in prompt


@pytest.mark.parametrize("damage", ["role", "name", "direction", "intent_hash", "resolved_hash", "request", "query", "status"])
def test_interpretation_tampering_cannot_reach_response(damage):
    context, intent, resolved, _ = interpretation()
    change = {
        "role": {"person_roles": ("subject", "target")},
        "name": {"mentions": (("entity-1", "Other name", "unmatched"), context.mentions[1])},
        "direction": {"direction": ("entity-2", "entity-1")},
        "intent_hash": {"intent_hash": "b"*64}, "resolved_hash": {"resolved_hash": "b"*64},
        "request": {"request_id": "other-request"}, "query": {"search_text": "Other question"},
        "status": {"mentions": (("entity-1", "Bram", "resolved"), context.mentions[1])},
    }[damage]
    with pytest.raises(ValueError, match="routing_mismatch"):
        replace(context, **change).assert_routing(intent, resolved)


def test_question_evidence_and_historical_v1_payload_hash_remain_bound():
    context, _, _, evidence = interpretation()
    with pytest.raises(ValueError, match="response_mismatch"):
        context.assert_response("Tampered question", evidence)
    other = EvidenceBundleAssembler().current_context(request_id="request", request_scope_hash="c"*64)
    with pytest.raises(ValueError): context.freeze(other)
    with pytest.raises(ValueError): context.assert_response("Bram은 나를 어떻게 생각해?", other)
    old, _, _, _ = interpretation(named=False)
    expected = {"revision": "hybrid-admission.v1", "search_text": "Bram은 나를 어떻게 생각해?",
        "mentions": [{"ref": "entity-1", "mention": "Bram", "resolution": "unmatched"},
            {"ref": "entity-2", "mention": "진구", "resolution": "unmatched"}],
        "requested_direction": ("entity-1", "entity-2"), "direction_resolution": "ambiguous",
        "time_expression": None, "time_resolution": "not_requested", "applied_time_filter": None}
    assert old.provider_payload() == expected
    historical_hash = sha256(json.dumps({"binding": [old.request_id, old.intent_hash, old.resolved_hash,
        old.user_message_hash, old.request_scope_hash, old.evidence_hash], "data": expected},
        ensure_ascii=True, sort_keys=True).encode()).hexdigest()
    assert old.content_hash == historical_hash and old.person_roles == ()
    with pytest.raises(ValueError, match="roles_invalid"): replace(old, person_roles=("actor", "target"))
    with pytest.raises(ValueError, match="mutable_input"): replace(context, mentions=list(context.mentions))
    with pytest.raises(ValueError, match="roles_invalid"): replace(context, person_roles=["actor", "target"])


@pytest.mark.parametrize("question,name", [
    ("Bram은 나를 어떻게 생각해?", "진구🙂"), ("What does Bram think of me?", "Jingu🙂"),
    ('Bram dijo "yo". ¿Qué piensa de mí?', "ジング🙂"),
])
def test_first_call_language_neutral_identity_and_actual_sdk_descriptions(monkeypatch, question, name):
    from app.providers.gemini import _native_parameters
    calls = []
    people = ChatIdentityContext("p-owner", "p-world", "p-thread", ChatPerson("p-requester", name), ChatPerson("p-responding", "Bram"))
    args = arguments(); args["entities"][1]["mention"] = name; args["relationship"]["to_name"] = name
    async def provider(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text="", finish_reason="STOP", tool_calls=(ProviderToolCall("CANONICAL", args, "native-name"),), usage={})
    monkeypatch.setattr(direct_llm, "generate_text", provider)
    selector = DirectLlmSupervisorSelectionProvider(material(), native_controls=True, code_coordination=True,
        social_context_mode=True, hybrid_recall=True)
    result = asyncio.run(selector.route(RetrievalRouterRequest(user_message=question,
        chat_identity=people, selection_protocol=NAME_SELECTION_PROTOCOL)))
    assert result.argument_protocol == NAME_SELECTION_PROTOCOL
    prompt = calls[0]["system_prompt"]
    assert "chat_participants.user.name exactly, without translation or transliteration" in prompt
    assert prompt.count(CHAT_PARTICIPANT_INSTRUCTIONS) == 1 and "must be fresh aliases" not in prompt
    view = json.loads(calls[0]["user_prompt"])
    assert view["chat_participants"]["user"]["name"] == name
    assert view["user_message"]["content"] == name + ": " + question
    declarations = [_native_parameters(tool.parameters) for tool in calls[0]["tools"]]
    assert sum(json.dumps(schema.model_dump(mode="json")).count(person_role_description()) for schema in declarations) == 1
    for schema in declarations:
        assert set(schema.properties["entities"].items.properties) == {"mention", "role"}
        assert set(schema.properties["entities"].items.properties["role"].enum) == PERSON_ROLES
        assert schema.properties["relationship"].nullable is True
        assert "from_name" in schema.properties["relationship"].properties


def test_shared_provider_keeps_concurrent_v1_v2_options_request_local(monkeypatch):
    seen = []
    async def provider(**kwargs):
        schema = kwargs["tools"][0].parameters
        named = "ref" not in schema["properties"]["entities"]["items"]["properties"]
        seen.append(named)
        await asyncio.sleep(0)
        args = arguments()
        if not named:
            for i, entity in enumerate(args["entities"], 1): entity["ref"] = f"entity-{i}"
            relation = args["relationship"]
            relation.pop("from_name"); relation.pop("to_name")
            relation.update({"from": "entity-1", "to": "entity-2"})
        return SimpleNamespace(text="", usage={}, finish_reason="STOP", tool_calls=(ProviderToolCall("CANONICAL", args, "concurrent-call"),))
    monkeypatch.setattr(direct_llm, "generate_text", provider)
    selector = DirectLlmSupervisorSelectionProvider(material(), native_controls=True, code_coordination=True,
        social_context_mode=True, hybrid_recall=True)
    async def run():
        return await asyncio.gather(*(selector.route(RetrievalRouterRequest(user_message="fixture",
            chat_identity=identity(), selection_protocol=protocol)) for protocol in
            (NAME_SELECTION_PROTOCOL, LEGACY_HYBRID_PROTOCOL, None, NAME_SELECTION_PROTOCOL)))
    results = asyncio.run(run())
    assert seen == [True, False, False, True] and not selector._argument_options.named_entities
    assert [result.argument_protocol for result in results] == [NAME_SELECTION_PROTOCOL, LEGACY_HYBRID_PROTOCOL,
        LEGACY_HYBRID_PROTOCOL, NAME_SELECTION_PROTOCOL]


@pytest.mark.parametrize("damage", ["role", "name", "endpoint"])
def test_named_failure_diagnostics_are_closed_and_unevaluated_stages_stay_unevaluated(monkeypatch, damage):
    args = arguments()
    if damage == "role": args["entities"][0]["role"] = "private-role-canary"
    if damage == "name": args["entities"][0]["mention"] = "private-name\ncanary"
    if damage == "endpoint": args["relationship"]["to_name"] = "private-endpoint-canary"
    async def provider(**kwargs):
        return SimpleNamespace(text="", usage={}, finish_reason="STOP", tool_calls=(ProviderToolCall("CANONICAL", args, "diagnostic"),))
    monkeypatch.setattr(direct_llm, "generate_text", provider)
    selector = DirectLlmSupervisorSelectionProvider(material(), native_controls=True, code_coordination=True,
        social_context_mode=True, hybrid_recall=True)
    with recording(True) as observation, pytest.raises(RetrievalRouterOutputError) as failure:
        asyncio.run(selector.route(RetrievalRouterRequest(user_message="private-question-canary",
            chat_identity=identity(), selection_protocol=NAME_SELECTION_PROTOCOL)))
    trace = failure.value.selection_validation["stages"]
    assert trace["meaning"] == "not_evaluated" and trace["coordination"] == "not_evaluated"
    assert failure.value.argument_protocol == NAME_SELECTION_PROTOCOL
    data = json.dumps(observation.details)
    assert "private-" not in data and "Bram" not in data and "진구" not in data and "synthetic-key" not in data
    row = next(row for row in observation.details if row["event"] == "reference_failure")
    assert row["input_stage"] == "model_name_wire"
    attempt = next(row for row in observation.details if row["event"] == "selection_attempt")
    assert attempt["schema_protocol"] == NAME_SELECTION_PROTOCOL
    fields = next(row for row in observation.details if row["event"] == "selection_fields")
    assert fields["missing_keys"] == fields["extra_keys"] == 0
