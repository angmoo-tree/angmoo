"""Comparable bounded reads and bytes; fixture timing is not provider latency."""
from dataclasses import replace
import json
from statistics import median
from time import perf_counter

import pytest
from sqlalchemy import event

from chat import test_p8_l_p_evidence_response_streaming as f
from chat.test_p8_l_p_evidence_response_streaming import response_session
from chat.test_named_retrieval_resolution import setup_names, add_person, scope, identity
from chat.test_named_supervisor_selection import arguments, options, call
from chat.test_chat_identity_delivery import request as response_request
from app.domains.chat.contracts.supervisor_selection import parse_control_selection, NAME_SELECTION_PROTOCOL, SelectionArgumentOptions
from app.domains.chat.contracts.retrieval_router_provider import RetrievalRouterRequest
from app.domains.chat.contracts.recall_interpretation import RecallInterpretationContext, NAMED_ADMISSION_REVISION, text_hash
from app.domains.chat.contracts.recall_mode import ChatRecallMode
from app.domains.chat.service.evidence_assembly import EvidenceBundleAssembler
from app.integrations.llm.supervisor_selection import control_selection_tools, control_selection_system_prompt, selection_prompt
from app.integrations.llm.character_response_generator import _system_prompt, _user_prompt


def bytes_of(value):
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


@pytest.mark.parametrize("size", [32, 256])
def test_v1_v2_same_four_people_read_query_plan_and_prompt_cost(response_session, size):
    db = response_session; setup_names(db)
    for i in range(size-2): add_person(db, f"cost-{i:03}", f"Person {i}")
    # Equal labels in this controlled cost fixture make both historical global
    # matching and new World matching return the very same three candidates.
    for identifier, name in (("p-responding-character", "Bram"), ("p-requester-character", "진구"),
                            ("character-cost-000", "Person 0")):
        db.get(f.models.Character, identifier).name = name
    db.commit(); policy, canonical, _ = scope(db)
    mentions = tuple((f"entity-{i+1}", name) for i, name in enumerate(("Bram", "진구", "Person 0", "Missing")))
    measures = {}
    for named in (False, True):
        sql, timings = [], []
        def collect(_conn, _cursor, statement, parameters, _context, _many): sql.append((statement, parameters))
        event.listen(db.bind, "before_cursor_execute", collect)
        try:
            for _ in range(3):
                start = perf_counter()
                result = (policy.resolve_named_entity_mentions(canonical, mentions, chat_identity=identity()) if named
                    else policy.resolve_entity_mentions(canonical, mentions))
                timings.append((perf_counter() - start) * 1000)
        finally: event.remove(db.bind, "before_cursor_execute", collect)
        assert len(sql) == 21 and sum(len(item.candidates) for item in result) == 3
        read = next((text, params) for text, params in sql if text.startswith("SELECT world_characters.id"))
        plan = db.connection().exec_driver_sql("EXPLAIN QUERY PLAN " + read[0], read[1]).all()
        assert any("ix_world_characters_world_status" in str(row) for row in plan)
        measures["v2" if named else "v1"] = {"sql_per_resolution": len(sql)//3, "returned_candidates": 3,
            "median_ms": round(median(timings), 3), "candidate_read_limit": 6 if named else 5,
            "query_plan": [row[3] for row in plan]}
    old_options = SelectionArgumentOptions(code_coordination=True, social_context_mode=True, hybrid_recall=True)
    raw = arguments(); raw["entities"] += [{"mention": "Person 0", "role": "counterpart"}, {"mention": "Missing", "role": "mentioned_third_party"}]
    intent = parse_control_selection("", (call(raw),), options=options())
    resolved = f._resolved(intent, "request")
    evidence = EvidenceBundleAssembler().current_context(request_id="request", request_scope_hash="a"*64)
    contexts = {}
    for named in (False, True):
        interpretation = RecallInterpretationContext("request", intent.envelope_hash, resolved.envelope_hash,
            text_hash(raw["search_text"]), raw["search_text"], tuple((ref, name, "unmatched") for ref, name in mentions),
            ("entity-1", "entity-2"), None, "not_requested", "ambiguous", None,
            **({"revision": NAMED_ADMISSION_REVISION, "person_roles": tuple(e.role for e in intent.entities)} if named else {})).freeze(evidence)
        options_used = options() if named else old_options
        router_request = RetrievalRouterRequest(user_message=raw["search_text"], chat_identity=identity(),
            selection_protocol=NAME_SELECTION_PROTOCOL if named else None)
        final = replace(response_request(raw=raw["search_text"], participants=identity(), bundle=evidence),
            recall_mode=ChatRecallMode.SOCIAL_HYBRID, recall_interpretation=interpretation)
        measures["v2" if named else "v1"].update({
            "tools_bytes": bytes_of([{"name": t.name, "description": t.description, "parameters": t.parameters}
                for t in control_selection_tools(options_used)]),
            "router_system_bytes": len(control_selection_system_prompt(options_used).encode()),
            "router_user_bytes": len(selection_prompt(router_request).encode()),
            "interpretation_bytes": bytes_of(interpretation.provider_payload()),
            "crg_system_bytes": len(_system_prompt(final).encode()), "crg_user_bytes": len(_user_prompt(final).encode())})
        assert len(json.dumps(interpretation.provider_payload(), ensure_ascii=False)) < 6500
        contexts[named] = interpretation
    assert contexts[True].person_roles == tuple(e.role for e in intent.entities)
    print(json.dumps({"world_size": size, **measures}, ensure_ascii=False))
