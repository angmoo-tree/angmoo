"""P8-L-K deterministic preflight, resolution and policy-envelope use case."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
import re
from time import monotonic
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domains.chat.domain.call_tracker import LlmNode, RouteAwareCallTracker
from app.domains.chat.domain.resolved_envelope import (
    ResolvedEntityBinding,
    ResolvedRetrievalEnvelope,
    RetrievalHardCaps,
)
from app.domains.chat.domain.retrieval_intent import (
    RetrievalContractError,
    RetrievalDecision,
    RetrievalIntentEnvelope,
    RetrievalRoute,
    RetrievalTimeKind,
)
from app.domains.chat.domain.retrieval_router import (
    RetrievalRouterRepairExhaustedError,
    RouterFailureDiagnostic,
    router_validation_is_retryable,
)
from app.domains.chat.ports.retrieval_policy import (
    CanonicalRetrievalScope,
    RetrievalEntityResolution,
    RetrievalPolicyResolverPort,
    RetrievalPreflightCommand,
)
from app.domains.chat.ports.retrieval_router_provider import (
    RetrievalRouterContextMessage,
    RetrievalRouterOutputError,
    RetrievalRouterProviderPort,
    RetrievalRouterRequest,
)
from app.domains.memory.public import CANONICAL_PRIMITIVE_REGISTRY
from app.domains.relationships.public import GRAPH_RECALL_PRIMITIVE_REGISTRY


_ABSOLUTE_RANGE_RE = re.compile(
    r"^(?P<start>\d{4}-\d{2}-\d{2})\.\.(?P<end>\d{4}-\d{2}-\d{2})$"
)


@dataclass(frozen=True, slots=True)
class ClarificationCandidate:
    ref: str
    display_name: str
    handle: str


@dataclass(frozen=True, slots=True)
class ClarificationResolution:
    slot: str
    candidates: tuple[ClarificationCandidate, ...] = ()


@dataclass(frozen=True, slots=True)
class RetrievalRoutingMetrics:
    route: RetrievalRoute
    router_proposed_route: RetrievalRoute
    sufficiency_guard_reason: str | None
    first_pass_valid: bool
    repair_used: bool
    rejected: bool
    clarification: bool
    entity_resolution_outcome: str
    direction_resolution_outcome: str
    time_resolution_outcome: str
    router_logical_calls: int
    router_physical_attempts: int
    provider: str
    model: str
    prompt_token_count: int | None = None
    output_token_count: int | None = None
    thought_token_count: int | None = None
    total_token_count: int | None = None
    latency_ms: int | None = None
    thinking_level: str | None = None
    max_output_tokens: int | None = None
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class RetrievalRoutingResult:
    intent: RetrievalIntentEnvelope
    resolved: ResolvedRetrievalEnvelope
    clarification: ClarificationResolution | None
    metrics: RetrievalRoutingMetrics
    call_tracker: dict


class RetrievalRoutingService:
    """Run one Router decision and code-own every canonical value."""

    def __init__(
        self,
        *,
        router: RetrievalRouterProviderPort,
        policy: RetrievalPolicyResolverPort,
        caps: RetrievalHardCaps | None = None,
    ) -> None:
        self._router = router
        self._policy = policy
        self._caps = caps or RetrievalHardCaps()

    async def route(
        self,
        command: RetrievalPreflightCommand,
        *,
        recent_context: tuple[RetrievalRouterContextMessage, ...] = (),
        today_sns_context: dict | None = None,
        now: datetime,
        deadline_at: datetime,
    ) -> RetrievalRoutingResult:
        if now.tzinfo is None or deadline_at.tzinfo is None:
            raise RetrievalContractError("retrieval_router_deadline_timezone_required")
        if now >= deadline_at:
            raise RetrievalContractError("retrieval_router_deadline_exceeded")

        # Deterministic canonical preflight happens before any provider call.
        scope = self._policy.load_scope(command)
        self._validate_scope_binding(command, scope)
        router_request = RetrievalRouterRequest(
            user_message=command.user_message,
            recent_context=recent_context,
            responding_character_name=scope.responding_character_name,
            world_language=scope.world_language,
            today_sns_context=today_sns_context,
        )

        first_physical = 0
        repair_physical = 0
        repair_used = False
        remaining_seconds = (deadline_at - now).total_seconds()
        started = monotonic()
        try:
            provider_result = await self._invoke_router(
                router_request, timeout_seconds=remaining_seconds
            )
            first_physical = provider_result.physical_attempt_count
        except RetrievalRouterOutputError as exc:
            first_physical = exc.physical_attempt_count
            repair_used = True
            remaining_seconds -= monotonic() - started
            if remaining_seconds <= 0:
                raise RetrievalContractError("retrieval_router_deadline_exceeded") from exc
            try:
                provider_result = await self._invoke_router(
                    replace(router_request, repair_diagnostic=exc.diagnostic),
                    timeout_seconds=remaining_seconds,
                )
            except RetrievalRouterOutputError as repaired_exc:
                terminal_code = repaired_exc.validation_code
                if not router_validation_is_retryable(exc.validation_code):
                    terminal_code = exc.validation_code
                raise RetrievalRouterRepairExhaustedError(
                    RouterFailureDiagnostic(
                        router_validation_code=terminal_code,
                        repair_used=True,
                        repair_exhausted=True,
                        physical_attempts=(
                            first_physical + repaired_exc.physical_attempt_count
                        ),
                    )
                ) from repaired_exc
            repair_physical = provider_result.physical_attempt_count

        original_intent = provider_result.intent
        intent, sufficiency_guard_reason = _apply_today_sns_sufficiency_guard(
            original_intent,
            user_message=command.user_message,
            today_sns_context=today_sns_context,
        )
        resolutions = self._policy.resolve_entity_mentions(
            scope,
            tuple((entity.ref, entity.mention) for entity in intent.entities),
        )
        resolution_by_ref = {item.ref: item for item in resolutions}
        if set(resolution_by_ref) != {entity.ref for entity in intent.entities}:
            raise RetrievalContractError("retrieval_entity_resolution_set_mismatch")

        clarification = self._clarification_from_scope_or_entities(
            intent=intent,
            scope=scope,
            resolutions=resolutions,
        )
        bindings = self._unique_safe_bindings(resolutions)
        binding_map = {binding.ref: binding.world_character_id for binding in bindings}

        time_from, time_to, time_outcome = self._resolve_time(
            intent=intent,
            scope=scope,
            now=now,
        )
        if time_outcome == "ambiguous" and clarification is None:
            clarification = ClarificationResolution(slot="time_scope")

        direction_from, direction_to, direction_outcome = self._resolve_direction(
            intent=intent,
            scope=scope,
            binding_map=binding_map,
        )
        if direction_outcome == "ambiguous" and clarification is None:
            clarification = ClarificationResolution(slot="relationship_direction")

        if clarification is not None and intent.route is not RetrievalRoute.CLARIFICATION:
            intent = self._as_clarification(intent, clarification.slot)
            direction_from = None
            direction_to = None
            time_from = None
            time_to = None
        elif intent.route is RetrievalRoute.CLARIFICATION and clarification is None:
            clarification = ClarificationResolution(
                slot=intent.clarification_slot or "entity_identity"
            )

        canonical_allowlist, graph_allowlist = self._operation_allowlists(intent.route)
        resolved = ResolvedRetrievalEnvelope.bind_intent(
            intent,
            request_id=scope.request_id,
            owner_id=scope.owner_id,
            world_id=scope.world_id,
            requester_world_character_id=scope.requester_world_character_id,
            responding_world_character_id=scope.responding_world_character_id,
            entity_bindings=bindings,
            relationship_from_world_character_id=direction_from,
            relationship_to_world_character_id=direction_to,
            absolute_time_from=time_from,
            absolute_time_to=time_to,
            memory_enabled=scope.memory_enabled,
            canonical_operation_allowlist=canonical_allowlist,
            graph_operation_allowlist=graph_allowlist,
            caps=self._caps,
            membership_active=scope.membership_active,
            blocked=scope.blocked,
            visible=scope.visible,
            observable=scope.observable,
        )

        tracker = RouteAwareCallTracker(route=intent.route, deadline_at=deadline_at)
        tracker.record_logical_call(LlmNode.RETRIEVAL_ROUTER, now=now)
        for _ in range(first_physical):
            tracker.record_physical_attempt(LlmNode.RETRIEVAL_ROUTER, now=now)
        if repair_used:
            tracker.record_logical_call(
                LlmNode.RETRIEVAL_ROUTER, now=now, repair=True
            )
            for _ in range(repair_physical):
                tracker.record_physical_attempt(LlmNode.RETRIEVAL_ROUTER, now=now)

        metrics = RetrievalRoutingMetrics(
            route=intent.route,
            router_proposed_route=original_intent.route,
            sufficiency_guard_reason=sufficiency_guard_reason,
            first_pass_valid=not repair_used,
            repair_used=repair_used,
            rejected=False,
            clarification=intent.route is RetrievalRoute.CLARIFICATION,
            entity_resolution_outcome=self._entity_outcome(resolutions),
            direction_resolution_outcome=direction_outcome,
            time_resolution_outcome=time_outcome,
            router_logical_calls=1 + int(repair_used),
            router_physical_attempts=first_physical + repair_physical,
            provider=provider_result.provider,
            model=provider_result.model,
            prompt_token_count=provider_result.prompt_token_count,
            output_token_count=provider_result.output_token_count,
            thought_token_count=provider_result.thought_token_count,
            total_token_count=provider_result.total_token_count,
            latency_ms=provider_result.latency_ms,
            thinking_level=provider_result.thinking_level,
            max_output_tokens=provider_result.max_output_tokens,
            finish_reason=provider_result.finish_reason,
        )
        return RetrievalRoutingResult(
            intent=intent,
            resolved=resolved,
            clarification=clarification,
            metrics=metrics,
            call_tracker=tracker.snapshot(),
        )

    async def _invoke_router(
        self,
        request: RetrievalRouterRequest,
        *,
        timeout_seconds: float,
    ):
        try:
            async with asyncio.timeout(timeout_seconds):
                return await self._router.route(request)
        except TimeoutError as exc:
            raise RetrievalContractError("retrieval_router_deadline_exceeded") from exc

    @staticmethod
    def _validate_scope_binding(
        command: RetrievalPreflightCommand,
        scope: CanonicalRetrievalScope,
    ) -> None:
        expected = (
            command.request_id,
            command.owner_id,
            command.world_id,
            command.thread_id,
            command.requester_world_character_id,
            command.responding_world_character_id,
        )
        actual = (
            scope.request_id,
            scope.owner_id,
            scope.world_id,
            scope.thread_id,
            scope.requester_world_character_id,
            scope.responding_world_character_id,
        )
        if expected != actual:
            raise RetrievalContractError("retrieval_preflight_scope_binding_mismatch")
        if (
            not scope.membership_active
            or scope.blocked
            or not scope.visible
            or not scope.observable
        ):
            raise RetrievalContractError("retrieval_preflight_policy_denied")

    @staticmethod
    def _clarification_from_scope_or_entities(
        *,
        intent: RetrievalIntentEnvelope,
        scope: CanonicalRetrievalScope,
        resolutions: tuple[RetrievalEntityResolution, ...],
    ) -> ClarificationResolution | None:
        if scope.world_ambiguous:
            return ClarificationResolution(slot="world")
        for resolution in resolutions:
            safe = tuple(
                candidate
                for candidate in resolution.candidates
                if candidate.safe_for_clarification
            )
            if len(safe) != 1:
                return ClarificationResolution(
                    slot="entity_identity",
                    candidates=tuple(
                        ClarificationCandidate(
                            ref=resolution.ref,
                            display_name=candidate.display_name,
                            handle=candidate.handle,
                        )
                        for candidate in safe[:4]
                    ),
                )
        if intent.route is RetrievalRoute.CLARIFICATION:
            return ClarificationResolution(
                slot=intent.clarification_slot or "counterpart"
            )
        return None

    @staticmethod
    def _unique_safe_bindings(
        resolutions: tuple[RetrievalEntityResolution, ...],
    ) -> tuple[ResolvedEntityBinding, ...]:
        bindings: list[ResolvedEntityBinding] = []
        for resolution in resolutions:
            safe = [
                candidate
                for candidate in resolution.candidates
                if candidate.safe_for_clarification
            ]
            if len(safe) == 1:
                bindings.append(
                    ResolvedEntityBinding(
                        ref=resolution.ref,
                        world_character_id=safe[0].world_character_id,
                    )
                )
        return tuple(bindings)

    @staticmethod
    def _resolve_direction(
        *,
        intent: RetrievalIntentEnvelope,
        scope: CanonicalRetrievalScope,
        binding_map: dict[str, str],
    ) -> tuple[str | None, str | None, str]:
        relationship = intent.relationship
        if relationship is None:
            return None, None, "not_requested"
        semantic_ids = {
            "requester_character": scope.requester_world_character_id,
            "responding_character": scope.responding_world_character_id,
            **binding_map,
        }
        from_id = semantic_ids.get(relationship.from_ref)
        to_id = semantic_ids.get(relationship.to_ref)
        if from_id is None or to_id is None or from_id == to_id:
            return None, None, "ambiguous"
        return from_id, to_id, "resolved"

    @staticmethod
    def _resolve_time(
        *,
        intent: RetrievalIntentEnvelope,
        scope: CanonicalRetrievalScope,
        now: datetime,
    ) -> tuple[str | None, str | None, str]:
        meaning = intent.time_scope
        if meaning is None or meaning.kind is RetrievalTimeKind.HISTORICAL_UNSPECIFIED:
            return None, None, "not_requested"
        try:
            zone = ZoneInfo(scope.world_timezone)
        except ZoneInfoNotFoundError as exc:
            raise RetrievalContractError("retrieval_world_timezone_invalid") from exc
        local_now = now.astimezone(zone)
        start: datetime
        end: datetime
        if meaning.kind is RetrievalTimeKind.CURRENT_DAY:
            start = datetime.combine(local_now.date(), time.min, tzinfo=zone)
            end = local_now
        elif meaning.kind is RetrievalTimeKind.RECENT:
            start, end = local_now - timedelta(days=7), local_now
        elif meaning.kind is RetrievalTimeKind.RELATIVE:
            resolved = _relative_range(meaning.expression or "", local_now)
            if resolved is None:
                return None, None, "ambiguous"
            start, end = resolved
        elif meaning.kind is RetrievalTimeKind.ABSOLUTE_RANGE:
            match = _ABSOLUTE_RANGE_RE.fullmatch(meaning.expression or "")
            if match is None:
                return None, None, "ambiguous"
            try:
                start_day = date.fromisoformat(match.group("start"))
                end_day = date.fromisoformat(match.group("end"))
            except ValueError:
                return None, None, "ambiguous"
            if end_day < start_day or (end_day - start_day).days > 366:
                return None, None, "ambiguous"
            start = datetime.combine(start_day, time.min, tzinfo=zone)
            end = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=zone)
        else:  # pragma: no cover
            return None, None, "ambiguous"
        return _utc_iso(start), _utc_iso(end), "resolved"

    @staticmethod
    def _as_clarification(
        intent: RetrievalIntentEnvelope,
        slot: str,
    ) -> RetrievalIntentEnvelope:
        return RetrievalIntentEnvelope(
            decision=RetrievalDecision.CLARIFICATION,
            route=RetrievalRoute.CLARIFICATION,
            intent="clarification_required",
            entities=intent.entities,
            relationship=intent.relationship,
            time_scope=intent.time_scope,
            aggregation=intent.aggregation,
            coordination_hint=None,
            clarification_slot=slot,
        )

    @staticmethod
    def _operation_allowlists(
        route: RetrievalRoute,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        canonical = (
            tuple(sorted(operation.value for operation in CANONICAL_PRIMITIVE_REGISTRY))
            if route in {RetrievalRoute.CANONICAL, RetrievalRoute.BOTH}
            else ()
        )
        graph = (
            tuple(sorted(operation.value for operation in GRAPH_RECALL_PRIMITIVE_REGISTRY))
            if route in {RetrievalRoute.GRAPH, RetrievalRoute.BOTH}
            else ()
        )
        return canonical, graph

    @staticmethod
    def _entity_outcome(resolutions: tuple[RetrievalEntityResolution, ...]) -> str:
        if not resolutions:
            return "not_requested"
        counts = [
            sum(candidate.safe_for_clarification for candidate in item.candidates)
            for item in resolutions
        ]
        return "resolved" if all(count == 1 for count in counts) else "ambiguous"


def _relative_range(expression: str, local_now: datetime) -> tuple[datetime, datetime] | None:
    zone = local_now.tzinfo
    today = local_now.date()

    def day_range(day: date) -> tuple[datetime, datetime]:
        start = datetime.combine(day, time.min, tzinfo=zone)
        return start, start + timedelta(days=1)

    if expression == "어제":
        return day_range(today - timedelta(days=1))
    if expression == "사흘 전":
        return day_range(today - timedelta(days=3))
    if expression == "오늘 아침":
        start = datetime.combine(today, time.min, tzinfo=zone)
        return start, datetime.combine(today, time(hour=12), tzinfo=zone)
    if expression == "지난주":
        current_week = today - timedelta(days=today.weekday())
        start_day = current_week - timedelta(days=7)
        start = datetime.combine(start_day, time.min, tzinfo=zone)
        return start, start + timedelta(days=7)
    if expression == "지난달":
        current_month = today.replace(day=1)
        previous_last = current_month - timedelta(days=1)
        previous_month = previous_last.replace(day=1)
        return (
            datetime.combine(previous_month, time.min, tzinfo=zone),
            datetime.combine(current_month, time.min, tzinfo=zone),
        )
    return None


def _utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


_TODAY_MARKERS = ("오늘", "방금", "아까", "당일", "today")
_SNS_MARKERS = (
    "게시글",
    "글",
    "지저귐",
    "대꾸",
    "댓글",
    "답글",
    "좋아요",
    "리액션",
    "리포스트",
    "팔로우",
    "sns",
    "활동",
)
_RELATIONSHIP_MARKERS = ("관계", "사이", "친밀", "호감", "신뢰", "경로", "연결")


def _apply_today_sns_sufficiency_guard(
    intent: RetrievalIntentEnvelope,
    *,
    user_message: str,
    today_sns_context: dict | None,
) -> tuple[RetrievalIntentEnvelope, str | None]:
    """Finalize only Today-context sufficiency with bounded deterministic rules."""

    if intent.route in {
        RetrievalRoute.CLARIFICATION,
        RetrievalRoute.GRAPH,
        RetrievalRoute.BOTH,
    }:
        return intent, None
    normalized = " ".join(user_message.casefold().split())
    semantic_today = intent.time_scope is not None and intent.time_scope.kind is RetrievalTimeKind.CURRENT_DAY
    if intent.time_scope is not None and not semantic_today:
        return intent, None
    if not (semantic_today or any(marker in normalized for marker in _TODAY_MARKERS)) or not (
        intent.intent.startswith("today_") or any(marker in normalized for marker in _SNS_MARKERS)
    ):
        return intent, None
    if intent.relationship is not None or any(marker in normalized for marker in _RELATIONSHIP_MARKERS):
        return intent, None
    # The guard does not reinterpret another actor's identity or purpose. The
    # Router may choose CURRENT_CONTEXT with entity focus, but a CANONICAL
    # choice involving entities remains retrieval until the policy resolver.
    if intent.route is RetrievalRoute.CANONICAL and intent.entities:
        return intent, "today_semantic_focus_requires_retrieval"
    if not isinstance(today_sns_context, dict):
        return _intent_with_route(intent, RetrievalRoute.CANONICAL), "today_context_unavailable"
    entries = today_sns_context.get("entries")
    counts = today_sns_context.get("counts")
    coverage = today_sns_context.get("coverage")
    if not isinstance(entries, list) or not isinstance(counts, dict) or not isinstance(
        coverage, dict
    ):
        return _intent_with_route(intent, RetrievalRoute.CANONICAL), "today_context_invalid"
    relevant_kinds = _relevant_today_kinds(normalized)
    relevant_entries = [
        item
        for item in entries
        if isinstance(item, dict) and item.get("kind") in relevant_kinds
    ]
    known_count = sum(
        int(counts.get(kind) or 0)
        for kind in relevant_kinds
        if not isinstance(counts.get(kind), bool)
    )
    incomplete = any(
        coverage.get(kind) not in {"complete", "unsupported"}
        for kind in relevant_kinds
    )
    exact_requested = any(
        marker in normalized
        for marker in ("정확", "원문", "전체", "전부", "그대로", "몇 시")
    )
    content_incomplete = any(
        not bool(item.get("content_complete")) or bool(item.get("truncated"))
        for item in relevant_entries
    )
    omitted = known_count > len(relevant_entries)
    if incomplete or not today_sns_context.get("counts_exact", True) or omitted or (exact_requested and content_incomplete):
        return _intent_with_route(intent, RetrievalRoute.CANONICAL), "today_context_incomplete"
    if known_count == 0:
        # A complete empty inventory is already a factual answer: there was no
        # matching activity today. Do not spend another LLM call searching for
        # something the canonical inventory proved absent.
        if all(coverage.get(kind) == "complete" for kind in relevant_kinds):
            return _intent_with_route(intent, RetrievalRoute.CURRENT_CONTEXT), "today_context_complete_empty"
        return _intent_with_route(intent, RetrievalRoute.CANONICAL), "today_context_missing"
    if not relevant_entries:
        return _intent_with_route(intent, RetrievalRoute.CANONICAL), "today_context_missing"
    return _intent_with_route(intent, RetrievalRoute.CURRENT_CONTEXT), "today_context_sufficient"


def _relevant_today_kinds(message: str) -> set[str]:
    kinds: set[str] = set()
    if any(marker in message for marker in ("게시글", "지저귐", "글")):
        kinds.add("posts_authored")
    if any(marker in message for marker in ("대꾸", "댓글", "답글")):
        kinds.update(("replies_authored", "replies_received", "mentions_received"))
    if any(marker in message for marker in ("좋아요", "리액션")):
        kinds.update(("reactions_given", "reactions_received"))
    if "리포스트" in message:
        kinds.add("reposts")
    if "팔로우" in message:
        kinds.add("follows")
    if not kinds or any(marker in message for marker in ("sns", "활동")):
        kinds.update(
            {
                "posts_authored",
                "replies_authored",
                "replies_received",
                "mentions_received",
                "reactions_given",
                "reactions_received",
                "reposts",
                "follows",
            }
        )
    return kinds


def _intent_with_route(
    intent: RetrievalIntentEnvelope,
    route: RetrievalRoute,
) -> RetrievalIntentEnvelope:
    if route is intent.route:
        return intent
    return replace(
        intent,
        decision=(
            RetrievalDecision.CURRENT_CONTEXT
            if route is RetrievalRoute.CURRENT_CONTEXT
            else RetrievalDecision.RETRIEVAL
        ),
        route=route,
        coordination_hint=None,
        clarification_slot=None,
    )


__all__ = [
    "ClarificationCandidate",
    "ClarificationResolution",
    "RetrievalRoutingMetrics",
    "RetrievalRoutingResult",
    "RetrievalRoutingService",
]
