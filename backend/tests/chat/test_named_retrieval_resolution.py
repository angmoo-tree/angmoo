"""Canonical World names, safe completeness and directed hybrid admission."""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json

import pytest
from sqlalchemy import event

from chat import test_p8_l_p_evidence_response_streaming as f
from chat.test_p8_l_p_evidence_response_streaming import response_session
from chat.test_named_supervisor_selection import arguments, options, call
from app.domains.chat.contracts.chat_identity_context import ChatIdentityContext, ChatPerson
from app.domains.chat.contracts.retrieval_policy import RetrievalPreflightCommand
from app.domains.chat.contracts.retrieval_router_provider import RetrievalRouterProviderResult
from app.domains.chat.contracts.supervisor_selection import parse_control_selection, NAME_SELECTION_PROTOCOL
from app.domains.chat.contracts.recall_mode import ChatRecallMode
from app.domains.chat.service.retrieval_routing import RetrievalRoutingService
from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
from app.runtime.chat.retrieval_policy import SqlAlchemyRetrievalPolicyResolver
from app.runtime.world_characters.creation_configuration import initialize_created_world_character


def rename(db, identifier, name, handle=None):
    row = db.get(WorldCharacterConfiguration, identifier)
    row.profile = {**row.profile, "display_name": name, **({"handle": handle} if handle else {})}
    db.flush()


def add_person(db, identifier, name, *, handle=None):
    character = f._character("character-" + identifier, "p-owner")
    db.add(character); db.flush()
    role = f.models.WorldCharacter(id=identifier, world_id="p-world", character_id=character.id,
        membership_id="p-owner-membership", status="active", control_mode="autonomous", autonomous_enabled=False)
    db.add(role); db.flush()
    initialize_created_world_character(db, character=character, world_character=role)
    rename(db, identifier, name, handle)
    return role


def identity():
    return ChatIdentityContext("p-owner", "p-world", "p-thread",
        ChatPerson("p-requester", "진구"), ChatPerson("p-responding", "Bram"))


def scope(db):
    command = RetrievalPreflightCommand("name-request", "p-owner", "p-world", "p-thread",
        "p-requester", "p-responding", "Bram은 나를 어떻게 생각해?")
    policy = SqlAlchemyRetrievalPolicyResolver(db)
    return policy, policy.load_scope(command), command


def setup_names(db):
    rename(db, "p-requester", "진구", "jingu")
    rename(db, "p-responding", "Bram", "bram")


def resolve(db, name, people=None):
    policy, canonical, _ = scope(db)
    return policy.resolve_named_entity_mentions(canonical, (("entity-1", name),), chat_identity=people or identity())[0]


def test_world_name_handle_and_frozen_rename_use_canonical_id(response_session):
    db = response_session; setup_names(db)
    assert resolve(db, "Bram").candidates[0].world_character_id == "p-responding"
    assert resolve(db, "@BRAM").candidates[0].world_character_id == "p-responding"
    assert resolve(db, "bram").status == "unmatched"
    assert resolve(db, "브람").status == "unmatched"
    assert resolve(db, "p-responding-character").status == "unmatched"
    rename(db, "p-responding", "Sky Captain")
    frozen = resolve(db, "Bram")
    assert frozen.status == "resolved" and frozen.candidates[0].world_character_id == "p-responding"
    add_person(db, "new-bram", "Bram")
    assert resolve(db, "Bram").status == "multiple"


def test_other_world_profile_and_same_named_participants_never_choose_an_identity(response_session):
    db = response_session; setup_names(db)
    original = db.get(f.models.World, "p-world")
    other = f.models.World(**{column.name: getattr(original, column.name) for column in original.__table__.columns})
    other.id = other.slug = other.create_idempotency_key = "other-name-world"
    db.add(other); db.flush()
    membership = f.models.WorldMembership(id="other-name-membership", world_id=other.id,
        user_id="p-responder-owner", role="member", status="active", joined_at=f.NOW)
    db.add(membership); db.flush()
    role = f.models.WorldCharacter(id="other-name-bram", world_id=other.id,
        character_id="p-responding-character", membership_id=membership.id, status="active",
        control_mode="autonomous", autonomous_enabled=False)
    db.add(role); db.flush()
    initialize_created_world_character(db, character=db.get(f.models.Character, role.character_id), world_character=role)
    rename(db, role.id, "Captain from another World")
    assert resolve(db, "Captain from another World").status == "unmatched"
    assert resolve(db, "Bram").status == "resolved"
    rename(db, "p-requester", "Alex"); rename(db, "p-responding", "Alex")
    people = ChatIdentityContext("p-owner", "p-world", "p-thread", ChatPerson("p-requester", "Alex"), ChatPerson("p-responding", "Alex"))
    assert resolve(db, "Alex", people).status == "multiple"
    assert resolve(db, "@jingu", people).candidates[0].world_character_id == "p-requester"


def test_selected_frozen_author_and_exact_unicode_spacing(response_session):
    db = response_session; setup_names(db)
    add_person(db, "selected-person", "李  雨🙂")
    people = identity().extend({"selected-person": "李  雨🙂"})
    assert resolve(db, "李 雨🙂").status == "unmatched"
    assert resolve(db, "李  雨🙂", people).status == "resolved"
    rename(db, "selected-person", "Renamed author")
    assert resolve(db, "李  雨🙂", people).candidates[0].world_character_id == "selected-person"
    add_person(db, "same-old-author", "李  雨🙂")
    assert resolve(db, "李  雨🙂", people).status == "multiple"


@pytest.mark.parametrize("damage", ["inactive", "left", "deleted", "moderated", "missing_profile"])
def test_frozen_name_never_restores_lost_eligibility(response_session, damage):
    db = response_session; setup_names(db)
    if damage == "inactive": db.get(f.models.WorldCharacter, "p-responding").status = "inactive"
    if damage == "left": db.get(f.models.WorldMembership, "p-responder-membership").status = "left"
    if damage == "deleted": db.get(f.models.Character, "p-responding-character").deleted_at = datetime.now(UTC)
    if damage == "moderated": db.get(f.models.Character, "p-responding-character").moderation_status = "blocked"
    if damage == "missing_profile": db.get(WorldCharacterConfiguration, "p-responding").profile = {"display_name": "Bram"}
    db.flush()
    policy, canonical, _ = scope(db) if damage == "missing_profile" else (SqlAlchemyRetrievalPolicyResolver(db), None, None)
    if canonical is None:
        from app.domains.chat.contracts.retrieval_policy import CanonicalRetrievalScope
        canonical = CanonicalRetrievalScope("name-request", "p-owner", "p-world", "p-thread", "p-requester",
            "p-responding", "Asia/Seoul", "ko", "Bram", True)
    result = policy.resolve_named_entity_mentions(canonical, (("entity-1", "Bram"),), chat_identity=identity())[0]
    assert result.status == "unavailable" and not result.complete


def test_incomplete_and_forbidden_duplicates_never_become_unique(response_session):
    db = response_session; setup_names(db)
    for i in range(6): add_person(db, f"alex-{i}", "Alex")
    result = resolve(db, "Alex")
    assert len(result.candidates) == 5 and not result.complete and result.status == "unavailable"
    assert RetrievalRoutingService._unique_safe_bindings((result,)) == ()
    add_person(db, "bram-twin", "Bram")
    policy, canonical, _ = scope(db)
    policy._blocked_query = lambda _db, **kw: kw["second_world_character_id"] == "bram-twin"
    result = policy.resolve_named_entity_mentions(canonical, (("entity-1", "Bram"),), chat_identity=identity())[0]
    assert result.status == "unavailable" and RetrievalRoutingService._unique_safe_bindings((result,)) == ()


@pytest.mark.parametrize("kind", ["normal", "one_person", "unknown", "same_id", "duplicate"])
def test_real_name_routing_is_advisory_and_direction_is_not_guessed(response_session, kind):
    db = response_session; setup_names(db)
    payload = arguments()
    if kind == "one_person":
        payload.update(entities=[{"mention": "진구", "role": "subject"}], relationship=None)
    if kind == "unknown": payload["entities"][0]["mention"] = payload["relationship"]["from_name"] = "Unknown"
    if kind == "same_id": payload["entities"][1]["mention"] = payload["relationship"]["to_name"] = "@bram"
    if kind == "duplicate": add_person(db, "bram-twin", "Bram")
    intent = parse_control_selection("", (call(payload),), options=options())
    class Router:
        async def route(self, request):
            assert request.selection_protocol == NAME_SELECTION_PROTOCOL
            return RetrievalRouterProviderResult(intent, "fixture", "fixture", 1, argument_protocol=NAME_SELECTION_PROTOCOL)
    policy, _, command = scope(db); now = datetime.now(UTC)
    result = asyncio.run(RetrievalRoutingService(router=Router(), policy=policy, recall_mode=ChatRecallMode.SOCIAL_HYBRID).route(
        command, selection_protocol=NAME_SELECTION_PROTOCOL, chat_identity=identity(), now=now, deadline_at=now+timedelta(seconds=30)))
    assert result.intent.route.value == "CANONICAL" and result.clarification is None
    assert result.resolved.responding_world_character_id == "p-responding"
    assert result.interpretation.direction_status == ("resolved" if kind == "normal" else "not_requested" if kind == "one_person" else "ambiguous")
    view = result.interpretation.provider_payload()
    assert view["mentions"][0]["role"] == payload["entities"][0]["role"]
    assert "entity-" not in json.dumps(view) and "p-responding" not in json.dumps(view)
    assert result.interpretation.revision == "hybrid-admission.v2"
    if kind == "normal":
        assert view["requested_direction"] == {"from_name": "Bram", "to_name": "진구"}
        with pytest.raises(ValueError, match="routing_mismatch"):
            replace(result.interpretation, person_roles=("target", "actor")).assert_routing(result.intent, result.resolved)


@pytest.mark.parametrize("size", [32, 256])
def test_name_queries_remain_bounded_in_small_and_large_world(response_session, size):
    db = response_session; setup_names(db)
    for i in range(size-2): add_person(db, f"scale-{i:03}", f"Person {i}")
    db.commit(); policy, canonical, _ = scope(db)
    sql = []
    def collect(_conn, _cursor, statement, parameters, _context, _many): sql.append((statement, parameters))
    event.listen(db.bind, "before_cursor_execute", collect)
    try:
        result = policy.resolve_named_entity_mentions(canonical, tuple((f"entity-{i+1}", name) for i,name in
            enumerate(("Bram", "진구", "Person 0", "Missing"))), chat_identity=identity())
    finally: event.remove(db.bind, "before_cursor_execute", collect)
    name_sql = [(text, params) for text, params in sql if "world_character_configurations.profile" in text]
    assert len(name_sql) == 4 and all("LIMIT" in text for text, _ in name_sql)
    assert len(sql) <= 8 and sum(len(r.candidates) for r in result) == 3
    plans = [db.connection().exec_driver_sql("EXPLAIN QUERY PLAN " + text, params).all() for text, params in name_sql]
    assert any("ix_world_characters_world_status" in str(row) for plan in plans for row in plan)
    print(json.dumps({"world_size": size, "sql_count": len(sql), "name_queries": len(name_sql),
        "returned_candidates": 3, "plan": [row[3] for row in plans[0]]}))


def test_world_clarification_preserves_named_direction_without_claiming_applied_ids(response_session):
    db = response_session; setup_names(db)
    intent = parse_control_selection("", (call(arguments()),), options=options())
    class Router:
        async def route(self, request):
            return RetrievalRouterProviderResult(intent, "fixture", "fixture", 1, argument_protocol=NAME_SELECTION_PROTOCOL)
    policy, canonical, command = scope(db)
    policy.load_scope = lambda _command: replace(canonical, world_ambiguous=True)
    now = datetime.now(UTC)
    result = asyncio.run(RetrievalRoutingService(router=Router(), policy=policy, recall_mode=ChatRecallMode.SOCIAL_HYBRID).route(
        command, selection_protocol=NAME_SELECTION_PROTOCOL, chat_identity=identity(), now=now, deadline_at=now+timedelta(seconds=30)))
    assert result.intent.route.value == "CLARIFICATION"
    assert result.resolved.relationship_from_world_character_id is None
    assert result.resolved.relationship_to_world_character_id is None
    assert result.interpretation.provider_payload()["requested_direction"] == {"from_name": "Bram", "to_name": "진구"}
    assert result.interpretation.direction_status == "ambiguous"
    result.interpretation.assert_routing(result.intent, result.resolved)


def test_named_router_deadline_cancels_await_before_resolution_or_late_output(response_session):
    from app.domains.chat.contracts.retrieval_intent import RetrievalContractError
    db = response_session; setup_names(db)
    stopped = asyncio.Event()
    class Router:
        async def route(self, request):
            assert request.selection_protocol == NAME_SELECTION_PROTOCOL
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
    policy, _, command = scope(db)
    policy.resolve_named_entity_mentions = lambda *args, **kw: pytest.fail("Deadline reached resolution")
    now = datetime.now(UTC)
    with pytest.raises(RetrievalContractError, match="deadline_exceeded"):
        asyncio.run(RetrievalRoutingService(router=Router(), policy=policy, recall_mode=ChatRecallMode.SOCIAL_HYBRID,
            before_named_provider=db.commit).route(command, selection_protocol=NAME_SELECTION_PROTOCOL,
                chat_identity=identity(), now=now, deadline_at=now+timedelta(milliseconds=5)))
    assert stopped.is_set() and not db.in_transaction()
