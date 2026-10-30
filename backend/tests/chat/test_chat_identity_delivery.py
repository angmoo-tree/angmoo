"""Participant presentation and historical evidence, using isolated data and mock I/O."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import event, select

from chat import test_p8_l_p_evidence_response_streaming as f
from chat.test_p8_l_p_evidence_response_streaming import response_session
from app.contracts.name_binding import NameBindingError
from app.domains.chat.contracts.chat_identity_context import ChatIdentityContext, ChatPerson, IDENTITY_KEY, presentation_name
from app.domains.chat.contracts.character_response_generator import CharacterResponseGeneratorRequest, CharacterResponseContextMessage
from app.domains.chat.contracts.relationship_evidence import (
    DELIVERY_KEY, RelationshipEvidenceBinding, RelationshipEvidenceDelivery, RelationshipCurrentRead, digest,
)
from app.domains.chat.relationship_evidence_policy import capture_delivery, validate_delivery, historical_read, restore_legacy_relationships
from app.domains.chat.service.evidence_assembly import EvidenceBundleAssembler
from app.domains.chat.service.social_context_inspector import social_context_inspector
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.relationships.contracts.graph_recall import GraphRecallScope
from app.domains.relationships.models.social import RelationshipState
from app.domains.relationships.service.graph_recall import GraphRecallService
from app.domains.relationships.service.social_context import SocialContextService
from app.runtime.graph_projection.relationship_graph_read import SqlAlchemyRelationshipGraphReadGateway
from app.runtime.chat.message_composition import evidence_service
from app.runtime.chat.evidence_reads import relationships_current
from app.integrations.llm.character_response_generator import _user_payload, _user_prompt, _system_prompt, DirectLlmCharacterResponseGenerator
from app.integrations.llm.chat_input_presentation import message_view, planner_view, router_view


def identity():
    return ChatIdentityContext("p-owner", "p-world", "p-thread", ChatPerson("p-requester", "지민🙂"), ChatPerson("p-responding", "Bram"))


def request(*, raw="응.", participants=None, bundle=None, social=None, context=()):
    return CharacterResponseGeneratorRequest(user_message=raw, profile=f.CharacterResponseProfile(*(["fixture"] * 8)),
        recent_context=context, evidence=bundle or EvidenceBundleAssembler().current_context(request_id="request", request_scope_hash="a"*64),
        chat_identity=participants, social_snapshot=social)


@pytest.mark.parametrize("raw", ["응.", "지민🙂: 응.", '"Bram: yes"', "a: b\n```py\nprint(1)\n```", "Yes, let's meet."])
def test_raw_source_and_hash_are_not_rewritten_by_prefix(raw):
    participants = identity()
    context = (CharacterResponseContextMessage("user", raw, source_id="1", author_id="p-requester"),
        CharacterResponseContextMessage("assistant", "알겠어.", source_id="2", author_id="p-responding"))
    item = request(raw=raw, participants=participants, context=context)
    raw_hash = sha256(raw.encode()).hexdigest()
    value = _user_payload(item)
    assert value["latest_user_message"] == {"role": "user", "name": "지민🙂", "content": "지민🙂: " + raw}
    assert value["recent_context"][1]["content"] == "Bram: 알겠어."
    assert item.user_message == raw and item.recent_context[0].content == raw
    assert sha256(item.user_message.encode()).hexdigest() == raw_hash
    assert not any(identifier in json.dumps(value, ensure_ascii=False) for identifier in participants.names)
    assert _user_prompt(item).endswith(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def test_name_data_unicode_controls_escape_and_unknown_author():
    name = presentation_name('민\n수\t"🙂"\u2028')
    assert name == '민수"🙂"'
    value = identity().extend({"old-thread-author": name})
    assert message_view(value, "user", "Old original", "old-thread-author")["name"] == name
    assert message_view(value, "user", "Unknown original", "unknown") == {"role": "user", "content": "Unknown original"}
    assert message_view(value, "user", "Unverified author") == {"role": "user", "content": "Unverified author"}
    assert json.loads(json.dumps(value.participants(), ensure_ascii=False)) == value.participants()
    assert value.extend({"old-thread-author": "renamed"}).names["old-thread-author"] == name
    assert "Name: see chat_participants.assistant" in _system_prompt(request(participants=value))


def test_names_shared_across_participants_and_selected_sections_receive_distinct_refs():
    from app.domains.chat.contracts.evidence_bundle import EvidenceItem, EvidenceKind, EvidenceLocator, EvidenceLocatorKind
    from app.domains.chat.contracts.response_request import RetrievalAxis
    participants = identity().extend({"different-person": identity().requester.name})
    item = EvidenceItem("other-person-relation", EvidenceKind.GRAPH_RELATIONSHIP, "Verified relation", None, (RetrievalAxis.GRAPH,),
        locator=EvidenceLocator(EvidenceLocatorKind.GRAPH_RELATIONSHIP, "relation", source_revision="8", actor_world_character_id="p-responding", target_world_character_id="different-person"))
    bundle = EvidenceBundleAssembler()._bundle(request_id="request", request_scope_hash="a"*64, route=f.RetrievalRoute.GRAPH, outcome=f.RetrievalOutcome.RELATIONSHIP_USED, candidates=(item,), preserve_rank_order=True)
    payload = _user_payload(request(participants=participants, bundle=bundle))
    assert payload["identity_links"] == [{"section": "frozen_evidence", "ref": "other-person-relation", "target_ref": "context_person_1", "name": identity().requester.name}]
    assert payload["chat_participants"]["user"]["ref"] == "requester_character"


@pytest.mark.parametrize("change", ["digest", "revision", "thread", "requester", "extra"])
def test_damaged_present_namespace_is_not_legacy(change):
    value = identity().to_dict()
    if change == "digest": value["digest"] = "x" * 64
    elif change == "extra": value["extra"] = 1
    elif change == "revision": value["revision"] = "chat_identity_context.v999"
    elif change == "thread": value["thread_id"] = "other-thread"
    else: value["requester"]["identifier"] = "p-responding"
    if change == "thread":
        material = {key: item for key, item in value.items() if key != "digest"}; value["digest"] = digest(material)
        parsed = ChatIdentityContext.read({IDENTITY_KEY: value})
        with pytest.raises(NameBindingError): parsed.assert_scope("p-owner", "p-world", "p-thread", "p-requester", "p-responding")
    else:
        with pytest.raises(NameBindingError): ChatIdentityContext.read({IDENTITY_KEY: value})
    assert ChatIdentityContext.read({}) is None


def test_router_and_planners_share_participants_without_native_message_names():
    participants = identity()
    router_request = SimpleNamespace(chat_identity=participants, user_message="나를 기억해?", recent_context=(), social_snapshot=None)
    router = router_view({"user_message": router_request.user_message}, router_request)
    planner = planner_view({"user_message": router_request.user_message}, participants.participants())
    final = _user_payload(request(raw=router_request.user_message, participants=participants))
    assert router["chat_participants"] == planner["chat_participants"] == final["chat_participants"]
    assert router["user_message"] == planner["user_message"] == final["latest_user_message"]
    assert all(set(value) == {"role", "name", "content"} for value in (router["user_message"], planner["user_message"]))


def _committed(db, *, tamper=False, with_graph=False, target_count=1, identity_mutation=None):
    db.get(f.models.Character, "p-responding-character").owner_id = "p-owner"
    now = datetime.now(UTC)
    relation = RelationshipState(id="delivered-state", world_id="p-world", actor_world_character_id="p-responding",
        target_world_character_id="p-requester", version=8, interaction_count=3, familiarity=22, affinity=12,
        trust=15, tension=2, perception="서로 약속을 지켜온 대화 상대", view_version=4, last_metric_at=now)
    db.add(relation)
    labels = {"p-requester": "당시 지민"}
    locators = [{"source_id": relation.id, "actor_world_character_id": "p-responding", "target_world_character_id": "p-requester"}]
    for index in range(1, target_count):
        character = f._character(f"p-target-character-{index}", "p-owner"); db.add(character); db.flush()
        role = f.models.WorldCharacter(id=f"p-target-{index}", world_id="p-world", character_id=character.id,
            membership_id="p-owner-membership", role_key="no_specific_role", status="active", control_mode="autonomous",
            owner_user_id=None, autonomous_enabled=False, version=1)
        db.add(role); db.flush()
        from app.runtime.world_characters.creation_configuration import initialize_created_world_character
        initialize_created_world_character(db, character=character, world_character=role)
        state = RelationshipState(id=f"delivered-state-{index}", world_id="p-world", actor_world_character_id="p-responding",
            target_world_character_id=role.id, version=8, interaction_count=3, familiarity=22, affinity=12, trust=15,
            tension=2, perception=None, view_version=4, last_metric_at=now)
        db.add(state); labels[role.id] = f"Person {index}"
        locators.append({"source_id": state.id, "actor_world_character_id": "p-responding", "target_world_character_id": role.id})
    db.commit()
    scope = GraphRecallScope("p-owner", "p-world", "p-responding")
    recall = GraphRecallService(SqlAlchemyRelationshipGraphReadGateway(db))
    provider = SocialContextService(lambda query: recall.execute(query, graph_projection_enabled=False))
    if target_count > 1:
        from app.domains.relationships.contracts.graph_recall import GraphRecallResult, GraphRecallStatus, GraphRecallSource
        fresh = relationships_current(db, MemoryScope("p-owner", "p-world", "p-responding"), tuple(locators))
        assert all(value.access_allowed for value in fresh.values()), {key: value.reason for key, value in fresh.items() if not value.access_allowed}
        def canonical_fixture(query):
            relations = tuple(value.relationship for value in fresh.values()
                if query.counterpart_world_character_id is None or value.relationship.target_world_character_id == query.counterpart_world_character_id)
            return GraphRecallResult(query.operation, GraphRecallStatus.READY, GraphRecallSource.CANONICAL_FALLBACK, relationships=relations)
        provider = SocialContextService(canonical_fixture)
    social = provider.prepare(scope, labels=labels, counterpart_id="p-requester", now=now)
    assert len(social.items) == target_count
    route = f.RetrievalRoute.GRAPH if with_graph else f.RetrievalRoute.CURRENT_CONTEXT
    record = f._request(db, route)
    from app.contracts.name_binding import NameBindingSnapshot
    binding = NameBindingSnapshot("p-owner", "p-world", "p-responding", "당시 Bram", "p-requester", "당시 지민", 0)
    row = db.get(f.models.ChatResponseRequest, record.request_id)
    row.node_state_json = json.dumps({"name_binding": binding.to_dict(), IDENTITY_KEY: ChatIdentityContext.from_binding(binding, "p-thread").extend(labels).to_dict()})
    if identity_mutation:
        state = json.loads(row.node_state_json); raw = state[IDENTITY_KEY]
        identity_mutation(raw)
        raw["digest"] = digest({key: value for key, value in raw.items() if key != "digest"})
        row.node_state_json = json.dumps(state)
    db.commit(); record = f.SqlAlchemyResponseLifecycleRepository(db).get_request(record.request_id)
    command = replace(f._command(record), social_snapshot=social)
    captures = []
    class Generator(f._Generator):
        async def generate(self, value):
            result = await super().generate(value)
            payload = _user_payload(value)
            proof = value.relationship_delivery_factory(payload, _user_prompt(value, payload=payload))
            if tamper: proof["items"][0]["name"] = "tampered"
            captures.append(proof)
            return replace(result, relationship_delivery=proof)
    class Router(f._Router):
        async def route(self, command, **kwargs):
            kwargs.pop("social_snapshot", None)
            return await super().route(command, **kwargs)
    workflow = f._workflow(db, route, Generator(), router=Router(route))
    if with_graph:
        from app.domains.relationships.contracts.graph_recall import GraphRecallResult, GraphRecallOperation, GraphRecallStatus, GraphRecallSource
        class Graph(f._Graph):
            async def plan_and_execute(self, command, **kwargs):
                result = await super().plan_and_execute(command, **kwargs)
                rows = GraphRecallResult(GraphRecallOperation.DIRECT_RELATIONSHIP, GraphRecallStatus.READY,
                    GraphRecallSource.CANONICAL_FALLBACK, relationships=tuple(item.relationship for item in social.items))
                return replace(result, execution=SimpleNamespace(results=(rows,)))
        workflow._graph = Graph()
    workflow._social_context_provider = provider
    events = asyncio.run(f._collect(workflow.run(command)))
    return record, relation, events, captures


def test_both_relationship_read_sections_keep_frozen_facts_and_names(response_session):
    record, relation, events, captures = _committed(response_session, with_graph=True)
    assert events[-1].event_type.value == "completed", events
    assert {item["section"] for item in captures[0]["items"]} == {"items", "current_context"}
    relation.version = 9; relation.view_version = 5; relation.perception = "Current different perception"; response_session.commit()
    read = evidence_service.get_world_response_evidence(response_session, response_session.get(f.models.User, "p-owner"), "p-world", "p-thread", record.request_id)
    assert len(read.items) == len(read.current_context) == 1
    for item in [*read.items, *read.current_context]:
        assert item.availability == "available" and item.relationship_change == "changed"
        assert item.related_character == "당시 지민" and item.relationship_projection.familiarity == 22
    assert read.read_limitations == [] and read.capability == "available"


@pytest.mark.parametrize("field", ["owner_id", "world_id", "thread_id"])
def test_valid_digest_but_wrong_identity_scope_fails_before_router_or_response_provider(response_session, field, monkeypatch):
    calls = []
    async def unexpected(*args, **kwargs): calls.append("provider"); raise AssertionError("provider must not run")
    monkeypatch.setattr(f._Generator, "generate", unexpected)
    monkeypatch.setattr(f._Router, "route", unexpected)
    with pytest.raises(NameBindingError, match="chat_identity_scope_invalid"):
        _committed(response_session, identity_mutation=lambda raw: raw.update({field: "other-scope"}))
    assert calls == []
    stored = f.SqlAlchemyResponseLifecycleRepository(response_session).get_request("request-current_context")
    assert stored.committed_assistant_message_id is None and DELIVERY_KEY not in stored.response_metadata


def test_committed_evidence_survives_eight_to_nine_and_rename_without_search_warning(response_session):
    db = response_session
    record, relation, events, captures = _committed(db)
    assert events[-1].event_type.value == "completed", events
    assert len(captures) == 1
    committed = f.SqlAlchemyResponseLifecycleRepository(db).get_request(record.request_id)
    assert DELIVERY_KEY in committed.response_metadata and committed.node_state.get("_situation_policy") is None
    owner = db.get(f.models.User, "p-owner")
    before = evidence_service.get_world_response_evidence(db, owner, "p-world", "p-thread", record.request_id)
    assert before.current_context[0].relationship_change == "same"
    relation.version = 9; relation.view_version = 5; relation.perception = "현재의 다른 인식"
    db.get(f.models.Character, "p-requester-character").name = "Renamed"; db.commit()
    statements = []
    def sql(_, __, text, ___, ____, _____): statements.append(text)
    event.listen(db.get_bind(), "before_cursor_execute", sql)
    try: after = evidence_service.get_world_response_evidence(db, owner, "p-world", "p-thread", record.request_id)
    finally: event.remove(db.get_bind(), "before_cursor_execute", sql)
    item = after.current_context[0]
    assert item.availability == "available" and item.relationship_change == "changed"
    assert item.related_character == "당시 지민" and item.relationship_projection.perception == "서로 약속을 지켜온 대화 상대"
    assert after.capability == "available" and after.read_limitations == []
    assert after.retrieval_limitations.partial_axes == [] and after.retrieval_limitations.degraded_reason is None
    assert "현재의 다른 인식" not in after.model_dump_json() and "target_id" not in after.model_dump_json()
    assert not any(sql.lstrip().upper().startswith(("UPDATE", "INSERT", "DELETE")) for sql in statements)
    assert f.SqlAlchemyResponseLifecycleRepository(db).get_request(record.request_id).response_metadata == committed.response_metadata


@pytest.mark.parametrize("mutation", ["same_facts", "lower_version", "lower_view", "metadata", "capture", "namespace_revision", "actor_binding", "path"])
def test_integrity_changes_never_expose_frozen_names_or_perceptions(response_session, mutation):
    db = response_session
    record, relation, events, _ = _committed(db)
    assert events[-1].event_type.value == "completed"
    row = db.get(f.models.ChatResponseRequest, record.request_id)
    if mutation == "same_facts": relation.affinity += 1
    elif mutation == "lower_version": relation.version = 7
    elif mutation == "lower_view": relation.view_version = 3
    elif mutation == "capture":
        state = json.loads(row.node_state_json); state["_relationship_delivery_capture"]["payload_digest"] = "0"*64; row.node_state_json = json.dumps(state)
    else:
        metadata = json.loads(row.response_metadata_json); proof = metadata[DELIVERY_KEY]
        if mutation == "namespace_revision": proof["revision"] = "unsupported"
        elif mutation == "actor_binding": proof["binding"]["actor_id"] = "other"
        elif mutation == "path": proof["items"][0]["path"] = "/fake/path"
        else: proof["items"][0]["fragment"] = "changed"
        row.response_metadata_json = json.dumps(metadata)
    db.commit()
    read = evidence_service.get_world_response_evidence(db, db.get(f.models.User, "p-owner"), "p-world", "p-thread", record.request_id)
    item = read.current_context[0]
    assert item.availability == "unavailable" and item.relationship_change is None
    assert item.excerpt is item.related_character is item.relationship_projection is item.canonical_href is None
    assert read.read_limitations == ["historical_unverified"]


def test_tampered_proof_rolls_back_answer_and_does_not_publish_receipt(response_session):
    db = response_session
    record, _, events, _ = _committed(db, tamper=True)
    assert events[-1].event_type.value == "failed"
    committed = f.SqlAlchemyResponseLifecycleRepository(db).get_request(record.request_id)
    assert committed.committed_assistant_message_id is None and DELIVERY_KEY not in committed.response_metadata
    assert db.scalar(select(f.models.MessageMessage).where(f.models.MessageMessage.role == "assistant")) is None


def test_discarded_missing_description_does_not_remove_committed_chat_relationship_proof(response_session):
    from app.contracts.environment import EnvironmentSnapshot
    from app.domains.memory.service.scope import MemoryScopeService
    from app.domains.memory.service.situation_policy import capture
    from app.domains.memory.models.activity_situation import MemorySituationReceipt
    from app.domains.memory.repository.situation_recovery import discard
    from app.domains.memory.policies.situation_output import parse_description
    from app.runtime.memory.composition import memory_repository
    from app.runtime.chat.situation_memory import ChatSituationMemory
    db = response_session
    scope = MemoryScope("p-owner", "p-world", "p-responding")
    settings = MemoryScopeService(memory_repository(db))
    setting = settings.get_or_create(scope)
    setting = settings.update(scope, expected_version=setting.version, enabled=True, retention_days=180)
    record, _, events, _ = _committed(db, with_graph=True)
    assert events[-1].event_type.value == "completed"
    # Receive the same committed activity using the real manifest and acceptance port.
    policy = capture(db, owner_id=scope.owner_id, world_id=scope.world_id, actor_id=scope.subject_world_character_id,
        environment=EnvironmentSnapshot(memory_search_locale="ko-KR"), policy="activity_situation")
    committed = f.SqlAlchemyResponseLifecycleRepository(db).get_request(record.request_id)
    command = replace(f._command(committed), preflight=replace(f._command(committed).preflight, user_message=db.get(f.models.MessageMessage, record.user_message_id).content))
    row = db.get(f.models.ChatResponseRequest, record.request_id)
    row.node_state_json = json.dumps({**json.loads(row.node_state_json), "_situation_policy": policy}); db.commit()
    command = replace(command, request=f.SqlAlchemyResponseLifecycleRepository(db).get_request(record.request_id))
    memory = ChatSituationMemory(db)
    bundle = EvidenceBundleAssembler().current_context(request_id=record.request_id, request_scope_hash=record.request_scope_hash)
    manifest = memory.freeze(command, bundle, _user_payload(request(raw=command.preflight.user_message, participants=ChatIdentityContext.read(command.request.node_state))))
    text = db.get(f.models.MessageMessage, committed.committed_assistant_message_id).content
    result = replace(asyncio.run(f._Generator().generate(request())), text=text, situation_manifest=manifest,
        situation_draft=parse_description(None, target_key=record.response_slot_id), situation_output_digest=sha256(text.encode()).hexdigest())
    memory.admit(command, committed, result)
    db.commit()
    receipt = db.scalar(select(MemorySituationReceipt))
    assert receipt.state == "blocked" and receipt.description_status == "missing"
    metadata_before = f.SqlAlchemyResponseLifecycleRepository(db).get_request(record.request_id).response_metadata
    discard(db, setting, sequence=receipt.sequence, expected_version=receipt.state_version, request_key="discard-missing-description", now=datetime.now(UTC)); db.commit()
    assert db.get(MemorySituationReceipt, receipt.sequence).state == "discarded"
    read = evidence_service.get_world_response_evidence(db, db.get(f.models.User, "p-owner"), "p-world", "p-thread", record.request_id)
    assert all(item.availability == "available" for item in [*read.items, *read.current_context])
    assert f.SqlAlchemyResponseLifecycleRepository(db).get_request(record.request_id).response_metadata == metadata_before


@pytest.mark.parametrize("field", ["owner_id", "world_id", "thread_id", "requester_id", "request_id", "request_scope_hash", "response_slot_id", "generation_id", "attempt_number"])
def test_other_delivery_binding_is_rejected_even_with_recomputed_digest(response_session, field):
    db = response_session
    record, _, events, _ = _committed(db, with_graph=True)
    assert events[-1].event_type.value == "completed"
    row = db.get(f.models.ChatResponseRequest, record.request_id)
    metadata = json.loads(row.response_metadata_json)
    proof = metadata[DELIVERY_KEY]
    proof["binding"][field] = 2 if field == "attempt_number" else "another-binding"
    proof["digest"] = digest({key: value for key, value in proof.items() if key != "digest"})
    row.response_metadata_json = json.dumps(metadata); db.commit()
    read = evidence_service.get_world_response_evidence(db, db.get(f.models.User, "p-owner"), "p-world", "p-thread", record.request_id)
    assert all(item.availability == "unavailable" and item.excerpt is item.related_character is item.relationship_projection is item.canonical_href is None for item in [*read.items, *read.current_context])


@pytest.mark.parametrize("mutation", ["moderation", "deleted", "membership", "state_deleted", "inactive_autonomous", "inactive_owner"])
def test_canonical_authorization_keeps_original_filters_without_graph_projection(response_session, mutation):
    db = response_session
    record, relation, events, _ = _committed(db)
    assert events[-1].event_type.value == "completed"
    target = db.get(f.models.WorldCharacter, "p-requester")
    character = db.get(f.models.Character, target.character_id)
    if mutation == "moderation": character.moderation_status = "hidden"
    elif mutation == "deleted": character.deleted_at = datetime.now(UTC)
    elif mutation == "membership": db.get(f.models.WorldMembership, target.membership_id).status = "left"
    elif mutation == "state_deleted": db.delete(relation)
    elif mutation == "inactive_autonomous": target.status = "inactive"; target.control_mode = "autonomous"; target.owner_user_id = None
    else: target.status = "inactive"
    db.commit()
    locator = {"source_id": "delivered-state", "actor_world_character_id": "p-responding", "target_world_character_id": "p-requester"}
    value = relationships_current(db, MemoryScope("p-owner", "p-world", "p-responding"), (locator,))["delivered-state"]
    assert value.access_allowed is (mutation == "inactive_owner")


def test_legacy_current_inspector_alone_cannot_recover_perception(response_session):
    db = response_session
    record, _, events, _ = _committed(db)
    assert events[-1].event_type.value == "completed"
    row = db.get(f.models.ChatResponseRequest, record.request_id)
    value = json.loads(row.response_metadata_json); value.pop(DELIVERY_KEY); row.response_metadata_json = json.dumps(value); db.commit()
    read = evidence_service.get_world_response_evidence(db, db.get(f.models.User, "p-owner"), "p-world", "p-thread", record.request_id)
    assert read.current_context[0].availability == "unavailable" and read.current_context[0].excerpt is None


def test_not_checked_requires_fresh_access_and_never_bypasses_denial(response_session):
    record, _, _, captures = _committed(response_session)
    item = RelationshipEvidenceDelivery.from_dict(captures[0]).items[0]
    assert historical_read(item, RelationshipCurrentRead(True)).change == "not_checked"
    assert historical_read(item, RelationshipCurrentRead(False)).excerpt is None


@pytest.mark.parametrize("async_factory", [False, True])
def test_adapter_builds_once_and_binds_both_receipts_to_actual_serialization(monkeypatch, async_factory):
    from app.domains.identity.contracts import CredentialMaterial, CredentialPurpose
    from app.integrations import direct_llm
    from app.domains.memory.contracts.activity_situation import DeliveredInputManifest, SituationPolicySnapshot, DeliveredSourceEntry
    calls, fragments = [], []
    async def generate(**kwargs):
        assert len(fragments) == 1
        calls.append(kwargs)
        return direct_llm.DirectLlmResponse(text="", parsed={"text": "알겠어.", "situation_description": "약속을 확인했다."}, usage={}, finish_reason="STOP")
    monkeypatch.setattr(direct_llm, "generate_text", generate)
    item = request(participants=identity())
    def freeze(payload):
        fragments.append(payload)
        json_digest = digest(payload)
        snapshot = SituationPolicySnapshot(MemoryScope("p-owner", "p-world", "p-responding"), "setting", "epoch", 1, "ko-KR")
        source = DeliveredSourceEntry("CHAT_MESSAGE", "1", "1", "a"*64, sha256("응.".encode()).hexdigest(),
            "/latest_user_message/content", "core", 0, "p-world", thread_id="p-thread", delivery_payload_digest=json_digest)
        return DeliveredInputManifest("chat:a", snapshot, json_digest, (source,), "p-thread", version=2)
    binding = RelationshipEvidenceBinding("p-owner", "p-world", "p-thread", "p-responding", "p-requester", "request", "a"*64, "slot", "generation", 1)
    async def freeze_async(payload):
        await asyncio.sleep(0)
        return freeze(payload)
    item = replace(item, situation_manifest_factory=freeze_async if async_factory else freeze, situation_locale="ko-KR", situation_target="slot",
        relationship_delivery_factory=lambda payload, prompt: capture_delivery(binding, item.evidence, None, payload, prompt))
    material = CredentialMaterial("fixture", "google", "gemini-3.1-flash-lite", "fixture", CredentialPurpose.MESSAGE_LLM, "fake")
    result = asyncio.run(DirectLlmCharacterResponseGenerator(material).generate(item))
    assert len(calls) == len(fragments) == 1 and "response_schema" in calls[0]
    assert result.text == "알겠어." and result.relationship_delivery["payload_digest"] == digest(fragments[0])
    prompt_digest = sha256(calls[0]["user_prompt"].encode()).hexdigest()
    assert result.relationship_delivery["prompt_digest"] == result.situation_manifest.payload_digest == prompt_digest
    assert all(source.delivery_payload_digest == prompt_digest for source in result.situation_manifest.sources)
    assert "chat_participants" not in calls[0]["response_schema"]["properties"]
