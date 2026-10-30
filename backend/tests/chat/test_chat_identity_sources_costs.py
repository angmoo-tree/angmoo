"""Source ownership, legacy read recovery and bounded local cost measurements."""
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
from statistics import median
import subprocess
from time import perf_counter
from types import ModuleType

import pytest
from sqlalchemy import event, select

from chat import test_p8_l_p_evidence_response_streaming as f
from chat.test_p8_l_p_evidence_response_streaming import response_session
from chat.test_chat_identity_delivery import _committed, identity, request
from app.domains.chat.contracts.chat_identity_context import ChatIdentityContext
from app.domains.chat.contracts.evidence_bundle import EvidenceItem, EvidenceKind, EvidenceLocator, EvidenceLocatorKind
from app.domains.chat.contracts.character_response_generator import CharacterResponseContextMessage
from app.domains.chat.contracts.relationship_evidence import DELIVERY_KEY
from app.domains.chat.contracts.response_request import RetrievalAxis
from app.domains.chat.contracts.today_sns_activity import TodaySnsActivityEntry
from app.domains.chat.service.evidence import EvidenceService
from app.domains.chat.service.evidence_assembly import EvidenceBundleAssembler
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.activity_situation import DeliveredInputManifest, DeliveredSourceEntry, RelationshipDeliveryBasis, SituationPolicySnapshot
from app.domains.memory.contracts.episode_packet import EpisodePacket, EpisodePacketUnit, EpisodePacketSource
from app.domains.memory.policies.episode_packets import bounded_episode_packets
from app.domains.social.models.feed import WorldCharacterBlock
from app.runtime.chat.message_composition import evidence_service
from app.runtime.chat.generation_workflows import character_names
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
from app.integrations.llm.character_response_generator import _user_payload, _user_prompt, _system_prompt


def test_verified_chat_original_authors_are_taken_from_original_thread_and_role(response_session):
    db = response_session
    original = db.scalar(select(f.models.MessageMessage).where(f.models.MessageMessage.role == "user"))
    answer = f.models.MessageMessage(thread_id="p-thread", role="assistant", content="Original answer", status="ok")
    db.add(answer); db.commit()
    identities = (("CHAT_MESSAGE", str(original.id)), ("CHAT_MESSAGE", str(answer.id)))
    scope = MemoryScope("p-owner", "p-world", "p-responding")
    details = RuntimeEpisodeDetailReader(db).read_sources(scope=scope, identities=identities)
    assert details[identities[0]].author_id == "p-requester"
    assert details[identities[1]].author_id == "p-responding"
    # A different current requester does not relabel the verified original.
    participants = ChatIdentityContext("p-owner", "p-world", "other-thread", replace(identity().requester, identifier="different-current-user"), identity().responder).extend({"p-requester": "Original World author"})
    assert participants.names[details[identities[0]].author_id] == "Original World author"
    original.content = "Changed original"; db.commit()
    changed = RuntimeEpisodeDetailReader(db).read_sources(scope=scope, identities=identities)
    assert changed[identities[0]].author_id == "p-requester"  # Repository compares saved digest before exporting it.


def test_private_episode_author_is_opaque_without_changing_original_text():
    from app.domains.memory.policies.episode_provider_view import episode_provider_view
    source = EpisodePacketSource("source", "user", "Original words", "verified")
    packet = EpisodePacket("memory", "Situation", "episode_v1", (EpisodePacketUnit("unit", (source,)),))
    named = replace(packet, units=(replace(packet.units[0], sources=(replace(source, author_id="private-world-character"),)),))
    for purpose in ("chat", "sns"):
        before = bounded_episode_packets(episode_provider_view((packet,)), purpose=purpose)
        after = bounded_episode_packets(episode_provider_view((named,)), purpose=purpose)
        assert 'private-world-character' not in after.text
        original = dict(before.packets[0]['units'][0]['sources'][0])
        attributed = dict(after.packets[0]['units'][0]['sources'][0])
        assert original.pop('author_ref') is None
        assert attributed.pop('author_ref').startswith('author-')
        assert attributed == original


def test_twenty_message_history_budget_includes_maximum_unicode_speaker_names(response_session):
    from app.domains.chat.contracts.chat_identity_context import ChatPerson
    from app.domains.chat.service.generation import _recent_context
    from app.integrations.llm.chat_input_presentation import message_view
    db = response_session
    participants = replace(identity(), requester=ChatPerson("p-requester", "민🙂"*40), responder=ChatPerson("p-responding", "B"*80))
    messages = [f.models.MessageMessage(thread_id="p-thread", role="user" if i%2 == 0 else "assistant", content=f"Original {i}: " + "x"*390, status="ok") for i in range(21)]
    db.add_all(messages); db.commit()
    router, response = _recent_context(db, "p-thread", exclude_message_id=messages[-1].id, identity=participants)
    assert 0 < len(response) <= 20 and len(router) == len(response)
    displayed = [message_view(participants, row.role, row.content, row.author_id) for row in response]
    assert sum(len(row["content"]) for row in displayed) <= 8000
    originals = {str(row.id): row.content for row in messages}
    assert all(row.content == originals[row.source_id] for row in response)
    assert str(messages[-1].id) not in {row.source_id for row in response}
    assert all(row["name"] == participants.names[source.author_id] for row, source in zip(displayed, response))


def test_today_quote_authors_are_distinct_and_omitted_excerpt_has_no_link():
    entry = TodaySnsActivityEntry("today-ref", "replies_authored", "reply", "post", "post-id", "a"*64, datetime.now(UTC),
        "Bram", "Elias", "full", "Reply title", "Bram reply", "Parent title", "Elias parent", "Root title", "Red root",
        "root-id", "post-id", "parent-id", True, False, None, actor_id="bram", counterpart_id="elias",
        source_authors=(("title", "bram"), ("body", "bram"), ("parent_title", "elias"), ("parent_body", "elias"), ("root_title", "red"), ("root_body", "red")))
    item = EvidenceBundleAssembler._today_item(entry)
    assert set(item.author_identities) == {("actor", "bram"), ("counterpart", "elias"), ("title", "bram"), ("body", "bram"), ("parent_title", "elias"), ("parent_body", "elias"), ("root_title", "red"), ("root_body", "red")}
    cut = EvidenceBundleAssembler._today_item(replace(entry, body="Long reply "*500))
    assert ("parent_body", "elias") in cut.author_identities and ("body", "bram") not in cut.author_identities
    titles_only = EvidenceBundleAssembler._today_item(replace(entry, body=None, parent_body=None, root_body=None))
    assert ("root_title", "red") in titles_only.author_identities and ("root_body", "red") not in titles_only.author_identities
    before = replace(entry, actor_id=None, counterpart_id=None, source_authors=()).provider_payload(include_content=True)
    assert before == entry.provider_payload(include_content=True)


def test_identical_names_and_metrics_do_not_merge_two_relationships():
    items = tuple(EvidenceItem(f"relation-{i}", EvidenceKind.GRAPH_RELATIONSHIP, "Same names and metrics", None,
        (RetrievalAxis.GRAPH,), locator=EvidenceLocator(EvidenceLocatorKind.GRAPH_RELATIONSHIP, f"state-{i}", source_revision="8", actor_world_character_id="actor", target_world_character_id=f"target-{i}")) for i in range(2))
    assert len(EvidenceBundleAssembler._dedupe_sort_truncate(items)) == 2


def test_current_canonical_block_hides_frozen_relationship(response_session):
    db = response_session
    record, _, events, _ = _committed(db, with_graph=True)
    assert events[-1].event_type.value == "completed"
    db.add(WorldCharacterBlock(id="test-block", world_id="p-world", blocker_world_character_id="p-requester", blocked_world_character_id="p-responding")); db.commit()
    from app.domains.chat.exceptions import MessageForbiddenError
    with pytest.raises(MessageForbiddenError):
        evidence_service.get_world_response_evidence(db, db.get(f.models.User, "p-owner"), "p-world", "p-thread", record.request_id)


def test_sufficient_legacy_graph_delivery_recovers_read_only_without_current_perception(response_session, monkeypatch):
    db = response_session
    record, relation, events, captures = _committed(db, with_graph=True)
    assert events[-1].event_type.value == "completed"
    raw = next(item for item in captures[0]["items"] if item["section"] == "items")
    basis = RelationshipDeliveryBasis(raw["state_id"], raw["actor_id"], raw["target_id"], raw["version"], raw["view_version"], raw["facts_digest"])
    source = DeliveredSourceEntry("RELATIONSHIP", raw["state_id"], "8", basis.facts_digest, sha256(raw["fragment"].encode()).hexdigest(), raw["path"], "background", 0, "p-world",
        actor_id=basis.actor_id, counterpart_id=basis.target_id, relationship_basis=basis, delivery_payload_digest="b"*64)
    manifest = DeliveredInputManifest(f"chat:{record.request_scope_hash}", SituationPolicySnapshot(MemoryScope("p-owner", "p-world", "p-responding"), "fixture-setting", "epoch", 1, "ko-KR"), "b"*64, (source,), "p-thread", version=2)
    row = db.get(f.models.ChatResponseRequest, record.request_id); metadata = json.loads(row.response_metadata_json); metadata.pop(DELIVERY_KEY); row.response_metadata_json = json.dumps(metadata)
    relation.version = 9; relation.perception = "Newest perception must remain hidden"; db.commit()
    monkeypatch.setattr(evidence_service.reads, "legacy_relationship_manifest", lambda *_: manifest)
    service = EvidenceService(evidence_service.thread_service, reads=evidence_service.reads)
    read = service.get_world_response_evidence(db, db.get(f.models.User, "p-owner"), "p-world", "p-thread", record.request_id)
    assert read.items[0].availability == "available" and read.items[0].relationship_change == "changed"
    assert read.items[0].relationship_projection.perception is None
    assert read.current_context[0].availability == "unavailable" and read.current_context[0].excerpt is None
    assert row.response_metadata_json == json.dumps(metadata)


def _shape(value, depth=0):
    if isinstance(value, dict):
        children = [_shape(v, depth+1) for v in value.values()]
        return (1+sum(x[0] for x in children), len(value)+sum(x[1] for x in children), max([depth, *[x[2] for x in children]]))
    if isinstance(value, list):
        children = [_shape(v, depth+1) for v in value]
        return (sum(x[0] for x in children), sum(x[1] for x in children), max([depth, *[x[2] for x in children]]))
    return (0, 0, depth)


def _timings(call, repetitions):
    durations=[]
    for _ in range(repetitions):
        started=perf_counter(); call(); durations.append((perf_counter()-started)*1000)
    return {"median_ms": round(median(durations), 3), "p95_ms": round(sorted(durations)[int(.95*(len(durations)-1))], 3)}


@pytest.mark.skipif(os.getenv("ANGMOO_MEASURE_CHAT_IDENTITY_COSTS") != "1", reason="Explicit local cost measurement requires the preserved baseline Git commit")
def test_bounded_input_and_relationship_read_costs(response_session, monkeypatch):
    db=response_session
    record, _, events, captures = _committed(db, with_graph=True, target_count=12)
    assert events[-1].event_type.value == "completed", events
    assert len(captures[0]["items"]) == 24
    baseline = ModuleType("chat_identity_baseline")
    original = subprocess.check_output(["git", "show", "51b73253:backend/app/domains/chat/service/evidence.py"], cwd=Path(__file__).resolve().parents[3]).decode("utf-8")
    exec(compile(original, "baseline_evidence.py", "exec"), baseline.__dict__)
    legacy_service = baseline.EvidenceService(evidence_service.thread_service, reads=evidence_service.reads)
    owner=db.get(f.models.User,"p-owner")
    from app.runtime.graph_projection.relationship_graph_read import SqlAlchemyRelationshipGraphReadGateway
    from app.domains.relationships.exceptions import GraphReadBackendError
    def no_graph(*args, **kwargs): raise GraphReadBackendError("graph_disabled")
    monkeypatch.setattr(SqlAlchemyRelationshipGraphReadGateway, "open_graph_repository", no_graph)
    counts={}
    times={}
    sizes={}
    visible={}
    for label, service in (("baseline",legacy_service),("after",evidence_service)):
        per_read=[]
        def call():
            db.expire_all(); statements=[]
            def sql(_,__,statement,___,____,_____): statements.append(statement)
            event.listen(db.get_bind(),"before_cursor_execute",sql)
            try: value=service.get_world_response_evidence(db, owner,"p-world","p-thread",record.request_id)
            finally: event.remove(db.get_bind(),"before_cursor_execute",sql)
            assert len(value.items)==len(value.current_context)==12
            visible[label]=sum(item.availability=="available" for item in [*value.items,*value.current_context])
            if label=="after": assert visible[label]==24
            assert not any(s.lstrip().upper().startswith(("INSERT","UPDATE","DELETE")) for s in statements)
            per_read.append(len(statements)); sizes[label]=len(value.model_dump_json().encode())
        call(); times[label]=_timings(call,20); counts[label]=sorted(set(per_read))
    assert max(counts["after"]) <= max(counts["baseline"])
    # Selected-name batches have constant query count, independent of duplicates.
    name_counts=[]
    for ids in (("p-requester",),("p-requester",)*100,tuple(["p-requester",*[f"p-target-{i}" for i in range(1,12)]])):
        statements=[]
        def sql(_,__,statement,___,____,_____): statements.append(statement)
        event.listen(db.get_bind(),"before_cursor_execute",sql)
        try: character_names(db,"p-world",ids)
        finally: event.remove(db.get_bind(),"before_cursor_execute",sql)
        name_counts.append(len(statements))
    assert len(set(name_counts))==1
    # A complete mixed final input, within existing 12 item / 8K history limits.
    committed=f.SqlAlchemyResponseLifecycleRepository(db).get_request(record.request_id)
    participants=ChatIdentityContext.read(committed.node_state).extend({"other-author":"원문 작성자🙂"})
    from app.domains.relationships.contracts.social_context import SocialContextItem, SocialContextSnapshot
    from app.domains.relationships.contracts.graph_recall import GraphRecallScope
    from app.runtime.chat.evidence_reads import relationships_current
    locators=tuple({"source_id":item["state_id"],"actor_world_character_id":item["actor_id"],"target_world_character_id":item["target_id"]} for item in captures[0]["items"] if item["section"]=="current_context")
    current=relationships_current(db,MemoryScope("p-owner","p-world","p-responding"),locators)
    social_items=tuple(SocialContextItem(value.relationship,participants.names[value.relationship.target_world_character_id],(),"canonical") for value in current.values())
    context_text="Selected outgoing relationships.\n"+"\n".join(item["fragment"] for item in captures[0]["items"] if item["section"]=="current_context")+"\n"
    social=SocialContextSnapshot("benchmark-social",GraphRecallScope("p-owner","p-world","p-responding"),datetime.now(UTC),social_items,"ready","partial",12,0,1,(),context_text,sha256(context_text.encode()).hexdigest())
    context=tuple(CharacterResponseContextMessage("user" if i%2==0 else "assistant", "Original bounded sentence. "*10, author_id="p-requester" if i%2==0 else "p-responding") for i in range(20))
    items=tuple(EvidenceItem(f"selected-{i}", [EvidenceKind.GRAPH_RELATIONSHIP,EvidenceKind.EPISODE_MEMORY,EvidenceKind.TODAY_SNS_ACTIVITY][i%3], "Verified bounded situation and original content. "*9, None, (RetrievalAxis.CANONICAL,), author_identities=(("original","other-author"),) if i%3!=0 else ()) for i in range(12))
    bundle=EvidenceBundleAssembler()._bundle(request_id="benchmark",request_scope_hash="a"*64,route=f.RetrievalRoute.CURRENT_CONTEXT,outcome=f.RetrievalOutcome.CURRENT_CONTEXT,candidates=items,preserve_rank_order=True)
    measurements={}
    for label, person in (("baseline",None),("after",participants)):
        value=request(raw="내가 보낸 약속을 기억해?",participants=person,bundle=bundle,context=context,social=social)
        payload=_user_payload(value); prompt=_user_prompt(value,payload=payload); system=_system_prompt(value)
        from app.providers.gemini import prepare_generate_request
        from app.providers.contracts import ProviderRequest
        native = prepare_generate_request(ProviderRequest("synthetic", "gemini-3.1-flash-lite", system, prompt, 1024, 45, thinking_level="high")).count_request("gemini-3.1-flash-lite")["generateContentRequest"]
        assert native["contents"] == [{"role": "user", "parts": [{"text": prompt}]}]
        measurements[label]={"objects":_shape(payload)[0],"keys":_shape(payload)[1],"depth":_shape(payload)[2],"logical_json_bytes":len(json.dumps(payload,ensure_ascii=False,separators=(",", ":")).encode()),
            "system_bytes":len(system.encode()),"user_prompt_bytes":len(prompt.encode()),"native_input_bytes":len(json.dumps(native,ensure_ascii=False,separators=(",", ":")).encode()),"native_shape":_shape(native),"assembly":_timings(lambda:_user_prompt(value),200)}
    report={"environment":"Windows Python 3.13, isolated in-memory SQLite; graph intentionally unavailable; no network/provider calls", "input":measurements,"relationship_12_plus_12":{"sql_counts":counts,"read_timings":times,"dto_bytes":sizes,"available_items":visible,"proof_bytes":len(json.dumps(captures[0],ensure_ascii=False).encode())},"selected_name_sql_counts":name_counts,"extra_ai_calls":0}
    output=Path(__file__).resolve().parents[3]/"artifacts/chat-identity-20261011/costs.json"; output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
