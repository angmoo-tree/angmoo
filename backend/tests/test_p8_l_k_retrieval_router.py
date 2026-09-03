from __future__ import annotations

import asyncio
from collections import Counter
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app import models
from app.core.db import Base
from app.domains.chat.application import RetrievalRoutingService
from app.domains.chat.domain import (
    ROUTER_VALIDATION_CODES,
    RetrievalContractError,
    RetrievalRoute,
    RetrievalRouterRepairExhaustedError,
    RouterFailureDiagnostic,
    normalize_router_validation_code,
    parse_retrieval_intent_payload,
    retrieval_router_response_schema,
)
from app.domains.chat.ports import (
    CanonicalRetrievalScope,
    RetrievalEntityCandidate,
    RetrievalEntityResolution,
    RetrievalPreflightCommand,
    RetrievalRouterOutputError,
    RetrievalRouterProviderResult,
    RetrievalRouterRequest,
)
from app.domains.identity.public import (
    CredentialMaterial,
    CredentialPurpose,
    LOCAL_INSTALLATION_KEY,
)
from app.integrations import direct_llm
from app.integrations.llm.retrieval_router import DirectLlmRetrievalRouterProvider
from app.providers.gemini import build_generate_content_config
from app.runtime.chat.retrieval_policy import SqlAlchemyRetrievalPolicyResolver


FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/p8_l/retrieval_topology_v1/held_out_ko.jsonl"
)
HOTFIX_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/p8_l/router_hotfix_v1/current_context_ko.jsonl"
)


def _payload(
    route: str = "BOTH",
    *,
    time_expression: str | None = "어제",
) -> dict:
    retrieval = route not in {"CURRENT_CONTEXT", "CLARIFICATION"}
    return {
        "version": "retrieval-intent.v1",
        "decision": (
            "RETRIEVAL"
            if retrieval
            else "CURRENT_CONTEXT"
            if route == "CURRENT_CONTEXT"
            else "CLARIFICATION"
        ),
        "route": route,
        "intent": (
            "current_context"
            if route == "CURRENT_CONTEXT"
            else "clarification_required"
            if route == "CLARIFICATION"
            else "relationship_cause"
        ),
        "entities": (
            []
            if route == "CURRENT_CONTEXT"
            else [{"ref": "entity-1", "mention": "철수", "role": "counterpart"}]
        ),
        "relationship": (
            None
            if route in {"CURRENT_CONTEXT", "CLARIFICATION"}
            else {
                "perspective": "responding_character",
                "from": "responding_character",
                "to": "entity-1",
                "dimension": "affinity",
                "requested_polarity": "conflict",
            }
        ),
        "time_scope": (
            None
            if route in {"CURRENT_CONTEXT", "CLARIFICATION"}
            else {"kind": "relative", "expression": time_expression}
        ),
        "aggregation": None,
        "coordination_hint": "GRAPH_THEN_CANONICAL" if route == "BOTH" else None,
        "clarification_slot": "entity_identity" if route == "CLARIFICATION" else None,
    }


class _FakeRouter:
    def __init__(self, *outcomes) -> None:
        self.outcomes = list(outcomes)
        self.requests = []

    async def route(self, request):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return RetrievalRouterProviderResult(
            intent=outcome,
            provider="fixture",
            model="fixture-router",
            physical_attempt_count=1,
        )


class _SlowRouter:
    async def route(self, _request):
        await asyncio.sleep(0.05)
        return RetrievalRouterProviderResult(
            intent=parse_retrieval_intent_payload(_payload("CURRENT_CONTEXT")),
            provider="fixture",
            model="fixture-router",
            physical_attempt_count=1,
        )


class _FakePolicy:
    def __init__(self, resolutions=(), *, world_ambiguous: bool = False) -> None:
        self.resolutions = tuple(resolutions)
        self.world_ambiguous = world_ambiguous
        self.load_calls = 0

    def load_scope(self, command):
        self.load_calls += 1
        return CanonicalRetrievalScope(
            request_id=command.request_id,
            owner_id=command.owner_id,
            world_id=command.world_id,
            thread_id=command.thread_id,
            requester_world_character_id=command.requester_world_character_id,
            responding_world_character_id=command.responding_world_character_id,
            world_timezone="Asia/Seoul",
            world_language="ko",
            responding_character_name="응답 앵무",
            memory_enabled=True,
            world_ambiguous=self.world_ambiguous,
        )

    def resolve_entity_mentions(self, _scope, mentions):
        if not mentions:
            return ()
        return self.resolutions


def _command() -> RetrievalPreflightCommand:
    return RetrievalPreflightCommand(
        request_id="request-1",
        owner_id="owner-1",
        world_id="world-1",
        thread_id="thread-1",
        requester_world_character_id="requester-1",
        responding_world_character_id="responding-1",
        user_message="철수와 어제 왜 싸웠지?",
    )


def _candidate(
    world_character_id: str,
    *,
    name: str = "철수",
    blocked: bool = False,
    active: bool = True,
    visible: bool = True,
    observable: bool = True,
) -> RetrievalEntityCandidate:
    return RetrievalEntityCandidate(
        world_character_id=world_character_id,
        display_name=name,
        handle=f"{world_character_id}-handle",
        active=active,
        blocked=blocked,
        visible=visible,
        observable=observable,
    )


def test_strict_router_parser_rejects_unknown_identity_and_raw_query_fields() -> None:
    intent = parse_retrieval_intent_payload(_payload())
    assert intent.route is RetrievalRoute.BOTH
    assert len(intent.envelope_hash) == 64

    with pytest.raises(RetrievalContractError, match="keys_invalid|forbidden_field"):
        parse_retrieval_intent_payload({**_payload(), "owner_id": "owner-1"})

    raw = _payload()
    raw["entities"][0]["mention"] = "MATCH (n) RETURN n"
    with pytest.raises(RetrievalContractError, match="raw_query_forbidden"):
        parse_retrieval_intent_payload(raw)

    unknown = _payload()
    unknown["relationship"]["direction"] = "outgoing"
    with pytest.raises(RetrievalContractError, match="relationship_keys_invalid"):
        parse_retrieval_intent_payload(unknown)


def test_router_failure_diagnostic_is_closed_bounded_and_never_copies_text() -> None:
    diagnostic = RouterFailureDiagnostic(
        router_validation_code="current_context_not_minimal",
        repair_used=True,
        repair_exhausted=True,
        physical_attempts=2,
    )
    assert diagnostic.retryable is True
    assert diagnostic.payload() == {
        "version": "router-diagnostic.v1",
        "node": "retrieval_router",
        "router_validation_code": "current_context_not_minimal",
        "repair_used": True,
        "repair_exhausted": True,
        "physical_attempts": 2,
    }
    assert "router_validation_unknown" in ROUTER_VALIDATION_CODES
    assert normalize_router_validation_code(
        "invalid because user said secret-message api-key-123"
    ) == "router_validation_unknown"

    with pytest.raises(RetrievalContractError, match="diagnostic_code_invalid"):
        RouterFailureDiagnostic(
            router_validation_code="user supplied arbitrary message",
            repair_used=True,
            repair_exhausted=True,
            physical_attempts=2,
        )
    with pytest.raises(RetrievalContractError, match="diagnostic_attempts_invalid"):
        RouterFailureDiagnostic(
            router_validation_code="json_decode_failed",
            repair_used=True,
            repair_exhausted=True,
            physical_attempts=1,
        )


def test_provider_schema_matches_parser_shape_and_serializes_for_gemini_families() -> None:
    schema = retrieval_router_response_schema()
    assert set(schema["required"]) == set(schema["properties"])
    assert "additionalProperties" not in schema
    nested_required = {
        "entities": {"ref", "mention", "role"},
        "relationship": {
            "perspective",
            "from",
            "to",
            "dimension",
            "requested_polarity",
        },
        "time_scope": {"kind", "expression"},
        "aggregation": {"kind", "target_role"},
    }
    for field, expected in nested_required.items():
        nested = schema["properties"][field]
        if field == "entities":
            nested = nested["items"]
        assert set(nested["required"]) == expected
        assert "additionalProperties" not in nested

    for model, thinking_key in (
        ("gemini-3.1-flash-lite", "thinkingLevel"),
        ("gemini-2.5-flash-lite", "thinkingBudget"),
    ):
        config = build_generate_content_config(
            model=model,
            system_prompt="router",
            max_output_tokens=1_024,
            response_mime_type="application/json",
            response_schema=schema,
            thinking_level="low",
        ).model_dump(by_alias=True, exclude_none=True)
        assert config["responseJsonSchema"] == schema
        assert "additionalProperties" not in json.dumps(
            config["responseJsonSchema"], sort_keys=True
        )
        assert thinking_key in config["thinkingConfig"]


def test_current_mood_hotfix_fixture_is_minimal_current_context() -> None:
    rows = [
        json.loads(line)
        for line in HOTFIX_FIXTURE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 3
    assert rows[0]["question"] == "안녕 지금 기분이 어때?"
    for row in rows:
        intent = parse_retrieval_intent_payload(row["expected"])
        assert intent.route is RetrievalRoute.CURRENT_CONTEXT
        assert intent.entities == ()
        assert intent.relationship is None
        assert intent.time_scope is None
        assert intent.aggregation is None
        assert intent.coordination_hint is None
        assert intent.clarification_slot is None


def test_current_context_routes_once_and_injects_no_retrieval_operations() -> None:
    intent = parse_retrieval_intent_payload(_payload("CURRENT_CONTEXT"))
    router = _FakeRouter(intent)
    service = RetrievalRoutingService(router=router, policy=_FakePolicy())
    now = datetime(2026, 9, 2, 4, tzinfo=UTC)

    result = asyncio.run(
        service.route(_command(), now=now, deadline_at=now + timedelta(seconds=30))
    )

    assert result.intent.route is RetrievalRoute.CURRENT_CONTEXT
    assert result.resolved.canonical_operation_allowlist == ()
    assert result.resolved.graph_operation_allowlist == ()
    assert result.resolved.intent_hash == result.intent.envelope_hash
    assert result.metrics.first_pass_valid is True
    assert result.call_tracker["logical_counts"]["retrieval_router"] == 1
    assert result.call_tracker["normal_full_path_cap"] == 2


def test_code_resolves_same_world_identity_direction_time_and_caps() -> None:
    intent = parse_retrieval_intent_payload(_payload("CANONICAL"))
    policy = _FakePolicy(
        (RetrievalEntityResolution("entity-1", (_candidate("canonical-cheolsu"),)),)
    )
    service = RetrievalRoutingService(router=_FakeRouter(intent), policy=policy)
    now = datetime(2026, 9, 2, 4, tzinfo=UTC)

    result = asyncio.run(
        service.route(_command(), now=now, deadline_at=now + timedelta(seconds=30))
    )

    assert result.intent.route is RetrievalRoute.CANONICAL
    assert result.resolved.entity_bindings[0].world_character_id == "canonical-cheolsu"
    assert result.resolved.relationship_from_world_character_id == "responding-1"
    assert result.resolved.relationship_to_world_character_id == "canonical-cheolsu"
    # World-local midnight is converted to an absolute UTC range by code.
    assert result.resolved.absolute_time_from == "2026-08-31T15:00:00Z"
    assert result.resolved.absolute_time_to == "2026-09-01T15:00:00Z"
    assert result.resolved.caps.max_hops == 3
    assert result.resolved.canonical_operation_allowlist
    assert result.resolved.graph_operation_allowlist == ()


def test_ambiguous_or_hidden_identity_becomes_safe_clarification_not_both() -> None:
    intent = parse_retrieval_intent_payload(_payload("BOTH"))
    ambiguous = RetrievalEntityResolution(
        "entity-1",
        (_candidate("cheolsu-a"), _candidate("cheolsu-b")),
    )
    now = datetime(2026, 9, 2, 4, tzinfo=UTC)
    result = asyncio.run(
        RetrievalRoutingService(
            router=_FakeRouter(intent), policy=_FakePolicy((ambiguous,))
        ).route(_command(), now=now, deadline_at=now + timedelta(seconds=30))
    )

    assert result.intent.route is RetrievalRoute.CLARIFICATION
    assert result.clarification is not None
    assert len(result.clarification.candidates) == 2
    assert result.resolved.entity_bindings == ()
    assert result.resolved.canonical_operation_allowlist == ()
    assert result.resolved.graph_operation_allowlist == ()
    assert result.call_tracker["normal_full_path_cap"] == 2

    hidden = RetrievalEntityResolution(
        "entity-1",
        (_candidate("hidden-id", blocked=True),),
    )
    hidden_result = asyncio.run(
        RetrievalRoutingService(
            router=_FakeRouter(intent), policy=_FakePolicy((hidden,))
        ).route(_command(), now=now, deadline_at=now + timedelta(seconds=30))
    )
    assert hidden_result.intent.route is RetrievalRoute.CLARIFICATION
    assert hidden_result.clarification is not None
    assert hidden_result.clarification.candidates == ()
    assert "hidden-id" not in json.dumps(
        hidden_result.clarification.__dict__ if hasattr(hidden_result.clarification, "__dict__") else {},
        ensure_ascii=False,
    )


def test_router_schema_repair_is_request_wide_and_at_most_once() -> None:
    valid = parse_retrieval_intent_payload(_payload("CURRENT_CONTEXT"))
    router = _FakeRouter(
        RetrievalRouterOutputError("current_context_not_minimal"),
        valid,
    )
    now = datetime(2026, 9, 2, 4, tzinfo=UTC)
    result = asyncio.run(
        RetrievalRoutingService(router=router, policy=_FakePolicy()).route(
            _command(), now=now, deadline_at=now + timedelta(seconds=30)
        )
    )
    assert result.metrics.first_pass_valid is False
    assert result.metrics.repair_used is True
    assert result.metrics.router_logical_calls == 2
    assert result.call_tracker["repair_node"] == "retrieval_router"
    assert router.requests[1].repair_diagnostic == "current_context_not_minimal"

    failing = _FakeRouter(
        RetrievalRouterOutputError("current_context_not_minimal"),
        RetrievalRouterOutputError("decision_route_mismatch"),
    )
    with pytest.raises(
        RetrievalRouterRepairExhaustedError, match="repair_exhausted"
    ) as exc_info:
        asyncio.run(
            RetrievalRoutingService(router=failing, policy=_FakePolicy()).route(
                _command(), now=now, deadline_at=now + timedelta(seconds=30)
            )
        )
    assert len(failing.requests) == 2
    diagnostic = exc_info.value.router_diagnostic
    assert diagnostic.router_validation_code == "decision_route_mismatch"
    assert diagnostic.repair_used is True
    assert diagnostic.repair_exhausted is True
    assert diagnostic.physical_attempts == 2
    assert diagnostic.retryable is True

    security = _FakeRouter(
        RetrievalRouterOutputError("forbidden_field"),
        RetrievalRouterOutputError("raw_query_forbidden"),
    )
    with pytest.raises(RetrievalRouterRepairExhaustedError) as security_info:
        asyncio.run(
            RetrievalRoutingService(router=security, policy=_FakePolicy()).route(
                _command(), now=now, deadline_at=now + timedelta(seconds=30)
            )
        )
    assert security_info.value.router_diagnostic.retryable is False

    first_attempt_security = _FakeRouter(
        RetrievalRouterOutputError("raw_query_forbidden"),
        RetrievalRouterOutputError("decision_route_mismatch"),
    )
    with pytest.raises(RetrievalRouterRepairExhaustedError) as first_security_info:
        asyncio.run(
            RetrievalRoutingService(
                router=first_attempt_security, policy=_FakePolicy()
            ).route(
                _command(), now=now, deadline_at=now + timedelta(seconds=30)
            )
        )
    assert (
        first_security_info.value.router_diagnostic.router_validation_code
        == "raw_query_forbidden"
    )
    assert first_security_info.value.router_diagnostic.retryable is False


def test_request_deadline_cancels_router_before_late_result_is_accepted() -> None:
    now = datetime(2026, 9, 2, 4, tzinfo=UTC)
    with pytest.raises(RetrievalContractError, match="deadline_exceeded"):
        asyncio.run(
            RetrievalRoutingService(router=_SlowRouter(), policy=_FakePolicy()).route(
                _command(),
                now=now,
                deadline_at=now + timedelta(milliseconds=1),
            )
        )


def _corpus_payload(expected: dict) -> dict:
    route = expected["route"]
    relationship = expected.get("relationship")
    time_scope = expected.get("time_scope")
    aggregation = expected.get("aggregation")
    aggregation_map = {
        "intersect_character_sets": ("group", "character_sets"),
        "rank_by_count": ("rank", "characters"),
        "compare_relationship_states": ("compare", "relationship_states"),
    }
    normalized_aggregation = None
    if aggregation is not None:
        kind, target = aggregation_map[aggregation["kind"]]
        normalized_aggregation = {"kind": kind, "target_role": target}
    return {
        "version": "retrieval-intent.v1",
        "decision": (
            "CURRENT_CONTEXT"
            if route == "CURRENT_CONTEXT"
            else "CLARIFICATION"
            if route == "CLARIFICATION"
            else "RETRIEVAL"
        ),
        "route": route,
        "intent": expected["intent"],
        "entities": expected.get("entities") or [],
        "relationship": (
            None
            if relationship is None
            else {
                "perspective": "responding_character",
                "from": relationship["from"],
                "to": relationship["to"],
                "dimension": None,
                "requested_polarity": None,
            }
        ),
        "time_scope": (
            None
            if time_scope is None
            else {
                "kind": time_scope["kind"],
                "expression": time_scope.get("mention"),
            }
        ),
        "aggregation": normalized_aggregation,
        "coordination_hint": expected.get("coordination_recipe"),
        "clarification_slot": (
            "entity_identity" if route == "CLARIFICATION" else None
        ),
    }


def test_held_out_ko_315_case_router_contract_is_executable() -> None:
    rows = [
        json.loads(line)
        for line in FIXTURE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    routes = Counter()
    for row in rows:
        intent = parse_retrieval_intent_payload(_corpus_payload(row["expected"]))
        routes[intent.route.value] += 1
        assert intent.intent == row["expected"]["intent"]
        assert len(intent.entities) == len(row["expected"]["entities"])
    assert len(rows) == 315
    assert routes == Counter(
        {"BOTH": 140, "GRAPH": 85, "CANONICAL": 50, "CLARIFICATION": 20, "CURRENT_CONTEXT": 20}
    )


def test_direct_llm_adapter_exposes_one_logical_call_without_hidden_json_retry(
    monkeypatch,
) -> None:
    captured = {}

    async def fake_generate_json(**kwargs):
        captured.update(kwargs)
        kwargs["tracker"].next_call_order()
        return kwargs["validator"](_payload("CURRENT_CONTEXT"))

    monkeypatch.setattr(
        "app.integrations.llm.retrieval_router.direct_llm.generate_json",
        fake_generate_json,
    )
    material = CredentialMaterial(
        credential_id="credential-1",
        provider="google",
        model="fixture-router",
        fingerprint="fingerprint",
        purpose=CredentialPurpose.MESSAGE_LLM,
        _secret="not-a-real-key",
    )
    result = asyncio.run(
        DirectLlmRetrievalRouterProvider(material).route(
            # Actual port value contains no canonical identity fields.
            RetrievalRouterRequest(user_message="지금 기분은 어때?")
        )
    )
    assert result.intent.route is RetrievalRoute.CURRENT_CONTEXT
    assert result.physical_attempt_count == 1
    assert captured["should_retry_json_error"](None, None, {}, 1) is False
    schema_text = json.dumps(captured["response_schema"], ensure_ascii=False)
    assert "owner_id" not in schema_text
    assert "world_id" not in schema_text
    assert "owner_id" not in captured["user_prompt"]
    assert "not-a-real-key" not in captured["user_prompt"]


def test_direct_llm_adapter_maps_domain_failure_to_safe_repair_code(
    monkeypatch,
) -> None:
    captured = {}

    async def fake_generate_json(**kwargs):
        captured.update(kwargs)
        kwargs["tracker"].next_call_order()
        try:
            raise RetrievalContractError(
                "retrieval_router_current_context_not_minimal"
            )
        except RetrievalContractError as cause:
            raise direct_llm.DirectLlmJsonError(
                "raw output must not escape",
                failure_class="json_parse_failed",
                parse_error_type="RetrievalContractError",
                attempt_count=1,
                last_payload={"conversation": "must-not-persist"},
            ) from cause

    monkeypatch.setattr(
        "app.integrations.llm.retrieval_router.direct_llm.generate_json",
        fake_generate_json,
    )
    material = CredentialMaterial(
        credential_id="credential-1",
        provider="google",
        model="gemini-3.1-flash-lite",
        fingerprint="fingerprint",
        purpose=CredentialPurpose.MESSAGE_LLM,
        _secret="not-a-real-key",
    )
    with pytest.raises(RetrievalRouterOutputError) as exc_info:
        asyncio.run(
            DirectLlmRetrievalRouterProvider(material).route(
                RetrievalRouterRequest(user_message="안녕 지금 기분이 어때?")
            )
        )
    assert exc_info.value.validation_code == "current_context_not_minimal"
    assert exc_info.value.diagnostic == "current_context_not_minimal"
    assert "must-not-persist" not in str(exc_info.value.__dict__)

    captured.clear()

    async def fake_repair(**kwargs):
        captured.update(kwargs)
        kwargs["tracker"].next_call_order()
        return kwargs["validator"](_payload("CURRENT_CONTEXT"))

    monkeypatch.setattr(
        "app.integrations.llm.retrieval_router.direct_llm.generate_json",
        fake_repair,
    )
    asyncio.run(
        DirectLlmRetrievalRouterProvider(material).route(
            RetrievalRouterRequest(
                user_message="안녕 지금 기분이 어때?",
                repair_diagnostic="current_context_not_minimal",
            )
        )
    )
    assert '"validation_code":"current_context_not_minimal"' in captured[
        "user_prompt"
    ]
    assert '"diagnostic"' not in captured["user_prompt"]
    assert "raw output must not escape" not in captured["user_prompt"]


def _user(user_id: str) -> models.User:
    return models.User(
        id=user_id,
        email=f"{user_id}@example.test",
        display_name=user_id,
        display_name_normalized=user_id,
        profile_setup_completed=True,
    )


def _character(character_id: str, owner_id: str, *, name: str, handle: str):
    return models.Character(
        id=character_id,
        owner_id=owner_id,
        name=name,
        handle=handle,
        one_liner="",
        personality="calm",
        speech_style="friendly",
        worldview="fixture",
        topic_preferences="chat",
        safety_rules="safe",
        status="active",
        moderation_status="active",
        execution_mode="local",
        persona_summary="fixture",
    )


@pytest.fixture
def retrieval_session() -> Session:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = Session(engine)
    now = datetime.now(UTC)
    owner = _user("router-owner")
    responder_owner = _user("router-responder-owner")
    third_owner = _user("router-third-owner")
    hidden_owner = _user("router-hidden-owner")
    requester_character = _character(
        "router-requester-character", owner.id, name="나", handle="router-me"
    )
    responding_character = _character(
        "router-responding-character",
        responder_owner.id,
        name="응답 앵무",
        handle="router-responder",
    )
    third_character = _character(
        "router-third-character", third_owner.id, name="철수", handle="cheolsu"
    )
    hidden_character = _character(
        "router-hidden-character",
        hidden_owner.id,
        name="철수",
        handle="hidden-cheolsu",
    )
    world = models.World(
        id="router-world",
        slug="router-world",
        owner_user_id=owner.id,
        name="Router World",
        tagline="",
        setting_description="",
        daily_life_description="",
        genre_tags=[],
        tone_tags=[],
        timezone="Asia/Seoul",
        language="ko",
        visibility="private",
        join_policy="private",
        status="published",
        contract_version="world-v1",
        contract_hash="a" * 64,
        readiness_status="publish_ready",
        create_idempotency_key="router-world",
    )
    memberships = [
        models.WorldMembership(
            id="router-owner-membership",
            world_id=world.id,
            user_id=owner.id,
            role="owner",
            status="active",
            joined_at=now,
        ),
        models.WorldMembership(
            id="router-responder-membership",
            world_id=world.id,
            user_id=responder_owner.id,
            role="member",
            status="active",
            joined_at=now,
        ),
        models.WorldMembership(
            id="router-third-membership",
            world_id=world.id,
            user_id=third_owner.id,
            role="member",
            status="active",
            joined_at=now,
        ),
        models.WorldMembership(
            id="router-hidden-membership",
            world_id=world.id,
            user_id=hidden_owner.id,
            role="member",
            status="active",
            joined_at=now,
        ),
    ]
    session.add_all([owner, responder_owner, third_owner, hidden_owner])
    session.flush()
    session.add_all(
        [
            requester_character,
            responding_character,
            third_character,
            hidden_character,
            world,
        ]
    )
    session.flush()
    session.add_all(memberships)
    session.flush()
    requester = models.WorldCharacter(
        id="router-requester",
        world_id=world.id,
        character_id=requester_character.id,
        membership_id=memberships[0].id,
        status="active",
        control_mode="owner_controlled",
        owner_user_id=owner.id,
        autonomous_enabled=False,
    )
    responding = models.WorldCharacter(
        id="router-responding",
        world_id=world.id,
        character_id=responding_character.id,
        membership_id=memberships[1].id,
        status="active",
        control_mode="autonomous",
        owner_user_id=None,
        autonomous_enabled=True,
    )
    third = models.WorldCharacter(
        id="router-cheolsu",
        world_id=world.id,
        character_id=third_character.id,
        membership_id=memberships[2].id,
        status="active",
        control_mode="autonomous",
        owner_user_id=None,
        autonomous_enabled=True,
    )
    hidden = models.WorldCharacter(
        id="router-hidden-cheolsu",
        world_id=world.id,
        character_id=hidden_character.id,
        membership_id=memberships[3].id,
        status="active",
        control_mode="autonomous",
        owner_user_id=None,
        autonomous_enabled=True,
    )
    session.add_all([requester, responding, third, hidden])
    session.flush()
    session.add(
        models.MessageThread(
            id="router-thread",
            requester_id=owner.id,
            character_id=responding_character.id,
            world_id=world.id,
            requester_world_character_id=requester.id,
            responding_world_character_id=responding.id,
            world_scope_status="resolved",
            selected_model="fixture-model",
        )
    )
    session.add(
        models.InstallationIdentity(
            singleton_key=LOCAL_INSTALLATION_KEY,
            installation_id="router-installation",
            owner_user_id=owner.id,
            bootstrap_state="claimed",
            claimed_at=now,
        )
    )
    session.add(
        models.MemoryScopeSettingModel(
            id="router-memory-setting",
            owner_id=owner.id,
            world_id=world.id,
            subject_world_character_id=responding.id,
            enabled=True,
        )
    )
    session.add(
        models.WorldCharacterBlock(
            id="router-hidden-block",
            world_id=world.id,
            blocker_world_character_id=responding.id,
            blocked_world_character_id=hidden.id,
        )
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_sqlalchemy_policy_injects_only_same_world_visible_unblocked_identity(
    retrieval_session: Session,
) -> None:
    command = RetrievalPreflightCommand(
        request_id="router-request",
        owner_id="router-owner",
        world_id="router-world",
        thread_id="router-thread",
        requester_world_character_id="router-requester",
        responding_world_character_id="router-responding",
        user_message="철수와 어제 왜 싸웠지?",
    )
    intent = parse_retrieval_intent_payload(_payload("CANONICAL"))
    now = datetime(2026, 9, 2, 4, tzinfo=UTC)
    result = asyncio.run(
        RetrievalRoutingService(
            router=_FakeRouter(intent),
            policy=SqlAlchemyRetrievalPolicyResolver(retrieval_session),
        ).route(command, now=now, deadline_at=now + timedelta(seconds=30))
    )

    assert result.intent.route is RetrievalRoute.CANONICAL
    assert result.resolved.owner_id == "router-owner"
    assert result.resolved.world_id == "router-world"
    assert result.resolved.memory_enabled is True
    assert [binding.world_character_id for binding in result.resolved.entity_bindings] == [
        "router-cheolsu"
    ]
    assert "router-hidden-cheolsu" not in result.resolved.payload().__repr__()
