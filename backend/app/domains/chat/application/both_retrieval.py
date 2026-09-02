"""Code-owned bounded coordination for the P8-L BOTH retrieval route."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import hashlib
from typing import Any

from app.domains.chat.application.canonical_retrieval import (
    CanonicalPlanningResult,
    CanonicalRetrievalCommand,
    CanonicalRetrievalPlanningService,
)
from app.domains.chat.application.graph_retrieval import (
    GraphPlanningResult,
    GraphRetrievalCommand,
    GraphRetrievalPlanningService,
)
from app.domains.chat.domain.call_tracker import (
    LlmNode,
    RouteAwareCallTracker,
    restore_call_tracker_snapshot,
)
from app.domains.chat.domain.resolved_envelope import ResolvedRetrievalEnvelope
from app.domains.chat.domain.retrieval_intent import (
    RetrievalContractError,
    RetrievalIntentEnvelope,
    RetrievalRoute,
)
from app.domains.chat.domain.workflow_recipe import (
    RetrievalWorkflow,
    WorkflowAxis,
    WorkflowDependencyBinding,
    WorkflowDependencyKind,
    WorkflowRecipe,
    WorkflowRecipeSelection,
    select_workflow_recipe,
)
from app.domains.memory.public import RecallDocumentKind
from app.domains.relationships.public import GraphRecallResult


@dataclass(frozen=True, slots=True)
class BothRetrievalCommand:
    user_message: str
    thread_id: str
    intent: RetrievalIntentEnvelope
    resolved: ResolvedRetrievalEnvelope
    call_tracker: Mapping[str, Any]
    graph_projection_enabled: bool = True

    def __post_init__(self) -> None:
        if not self.user_message.strip() or len(self.user_message) > 4_000:
            raise RetrievalContractError("both_retrieval_message_invalid")
        if not self.thread_id:
            raise RetrievalContractError("both_retrieval_thread_id_invalid")
        if not isinstance(self.graph_projection_enabled, bool):
            raise RetrievalContractError("both_retrieval_projection_flag_invalid")


@dataclass(frozen=True, slots=True)
class CoordinatedRetrievalReference:
    """Deterministically merged references, before P8-L-P Evidence assembly."""

    opaque_reference: str
    rank: int
    score: int
    axes: tuple[WorkflowAxis, ...]
    canonical_references: tuple[str, ...]
    graph_references: tuple[str, ...]
    event_references: tuple[str, ...]
    world_character_references: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkflowCoordinatorMetrics:
    requested_recipe: WorkflowRecipe
    selected_recipe: WorkflowRecipe
    router_hint_accepted: bool
    planners_parallel: bool
    planner_axes_called: tuple[WorkflowAxis, ...]
    dependency_reference: str | None
    downstream_short_circuited: bool
    downstream_short_circuit_reason: str | None
    input_candidate_count: int
    joined_reference_count: int
    dropped_unmatched_count: int
    deduplicated_count: int
    output_reference_count: int
    coordinator_llm_calls: int = 0


@dataclass(frozen=True, slots=True)
class BothRetrievalResult:
    request_id: str
    selection: WorkflowRecipeSelection
    workflow: RetrievalWorkflow | None
    dependency: WorkflowDependencyBinding | None
    canonical: CanonicalPlanningResult | None
    graph: GraphPlanningResult | None
    references: tuple[CoordinatedRetrievalReference, ...]
    metrics: WorkflowCoordinatorMetrics
    call_tracker: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _AxisCandidate:
    axis: WorkflowAxis
    axis_reference: str
    event_references: tuple[str, ...]
    world_character_references: tuple[str, ...]
    occurred_at: datetime | None


@dataclass(slots=True)
class _CandidateGroup:
    canonical_references: set[str]
    graph_references: set[str]
    event_references: set[str]
    world_character_references: set[str]
    occurred_at: datetime | None
    matched_event: bool = False
    matched_world_character: bool = False


class BothRetrievalWorkflowCoordinator:
    """Run exactly one of three bounded recipes without a coordinator LLM."""

    def __init__(
        self,
        *,
        canonical: CanonicalRetrievalPlanningService,
        graph: GraphRetrievalPlanningService,
    ) -> None:
        self._canonical = canonical
        self._graph = graph

    async def coordinate(
        self,
        command: BothRetrievalCommand,
        *,
        now: datetime,
        deadline_at: datetime,
    ) -> BothRetrievalResult:
        if now.tzinfo is None or deadline_at.tzinfo is None:
            raise RetrievalContractError("both_retrieval_deadline_timezone_required")
        if now >= deadline_at:
            raise RetrievalContractError("both_retrieval_deadline_exceeded")
        self._validate_command(command)
        tracker = restore_call_tracker_snapshot(
            command.call_tracker,
            deadline_at=deadline_at,
        )
        self._validate_start_tracker(tracker)
        selection = select_workflow_recipe(command.intent)

        canonical: CanonicalPlanningResult | None = None
        graph: GraphPlanningResult | None = None
        dependency: WorkflowDependencyBinding | None = None
        downstream_reason: str | None = None

        if selection.spec.planners_parallel:
            canonical, graph = await self._run_parallel(
                command,
                tracker=tracker,
                now=now,
                deadline_at=deadline_at,
            )
        elif selection.selected is WorkflowRecipe.GRAPH_THEN_CANONICAL:
            graph = await self._run_graph(
                command,
                tracker=tracker,
                now=now,
                deadline_at=deadline_at,
            )
            dependency = self._graph_event_dependency(command, graph)
            downstream_reason = self._downstream_reason(
                WorkflowAxis.CANONICAL,
                command.resolved,
                dependency,
                source_result=graph,
            )
            if downstream_reason is None:
                canonical = await self._run_canonical(
                    command,
                    tracker=tracker,
                    now=now,
                    deadline_at=deadline_at,
                    dependency=dependency,
                )
        else:
            canonical = await self._run_canonical(
                command,
                tracker=tracker,
                now=now,
                deadline_at=deadline_at,
            )
            dependency = self._canonical_character_dependency(command, canonical)
            downstream_reason = self._downstream_reason(
                WorkflowAxis.GRAPH,
                command.resolved,
                dependency,
                source_result=canonical,
            )
            if downstream_reason is None:
                graph = await self._run_graph(
                    command,
                    tracker=tracker,
                    now=now,
                    deadline_at=deadline_at,
                    dependency=dependency,
                )

        workflow = self._workflow(command, selection, canonical, graph)
        references, merge_stats = self._merge_references(
            command,
            selection=selection,
            canonical=canonical,
            graph=graph,
        )
        planner_axes_called = tuple(
            axis
            for axis, node in (
                (WorkflowAxis.CANONICAL, LlmNode.CANONICAL_PLANNER),
                (WorkflowAxis.GRAPH, LlmNode.GRAPH_PLANNER),
            )
            if tracker.logical_counts[node] > 0
        )
        return BothRetrievalResult(
            request_id=command.resolved.request_id,
            selection=selection,
            workflow=workflow,
            dependency=dependency,
            canonical=canonical,
            graph=graph,
            references=references,
            metrics=WorkflowCoordinatorMetrics(
                requested_recipe=selection.requested,
                selected_recipe=selection.selected,
                router_hint_accepted=selection.hint_accepted,
                planners_parallel=selection.spec.planners_parallel,
                planner_axes_called=planner_axes_called,
                dependency_reference=(
                    None if dependency is None else dependency.opaque_reference
                ),
                downstream_short_circuited=downstream_reason is not None,
                downstream_short_circuit_reason=downstream_reason,
                input_candidate_count=merge_stats["input"],
                joined_reference_count=merge_stats["joined"],
                dropped_unmatched_count=merge_stats["dropped"],
                deduplicated_count=merge_stats["deduplicated"],
                output_reference_count=len(references),
            ),
            call_tracker=tracker.snapshot(),
        )

    @staticmethod
    def _validate_command(command: BothRetrievalCommand) -> None:
        if command.intent.route is not RetrievalRoute.BOTH:
            raise RetrievalContractError("both_retrieval_route_invalid")
        if command.intent.envelope_hash != command.resolved.intent_hash:
            raise RetrievalContractError("both_retrieval_intent_hash_mismatch")
        intent_refs = {entity.ref for entity in command.intent.entities}
        resolved_refs = {binding.ref for binding in command.resolved.entity_bindings}
        if intent_refs != resolved_refs:
            raise RetrievalContractError("both_retrieval_entity_binding_mismatch")

    @staticmethod
    def _validate_start_tracker(tracker: RouteAwareCallTracker) -> None:
        if tracker.route is not RetrievalRoute.BOTH:
            raise RetrievalContractError("both_retrieval_tracker_route_mismatch")
        if tracker.logical_counts[LlmNode.RETRIEVAL_ROUTER] not in {1, 2}:
            raise RetrievalContractError("both_retrieval_router_call_missing")
        if any(
            tracker.logical_counts[node] != 0
            for node in (
                LlmNode.CANONICAL_PLANNER,
                LlmNode.GRAPH_PLANNER,
                LlmNode.CHARACTER_RESPONSE_GENERATOR,
            )
        ):
            raise RetrievalContractError("both_retrieval_tracker_already_started")
        if tracker.normal_full_path_cap != 4:
            raise RetrievalContractError("both_retrieval_call_cap_invalid")

    async def _run_parallel(
        self,
        command: BothRetrievalCommand,
        *,
        tracker: RouteAwareCallTracker,
        now: datetime,
        deadline_at: datetime,
    ) -> tuple[CanonicalPlanningResult, GraphPlanningResult]:
        outcomes = await asyncio.gather(
            self._run_canonical(
                command,
                tracker=tracker,
                now=now,
                deadline_at=deadline_at,
            ),
            self._run_graph(
                command,
                tracker=tracker,
                now=now,
                deadline_at=deadline_at,
            ),
            return_exceptions=True,
        )
        canonical, graph = outcomes
        if isinstance(canonical, BaseException):
            raise canonical
        if isinstance(graph, BaseException):
            raise graph
        return canonical, graph

    async def _run_canonical(
        self,
        command: BothRetrievalCommand,
        *,
        tracker: RouteAwareCallTracker,
        now: datetime,
        deadline_at: datetime,
        dependency: WorkflowDependencyBinding | None = None,
    ) -> CanonicalPlanningResult:
        return await self._canonical.plan_and_execute(
            CanonicalRetrievalCommand(
                user_message=command.user_message,
                thread_id=command.thread_id,
                intent=command.intent,
                resolved=command.resolved,
                call_tracker=command.call_tracker,
                workflow_dependency=dependency,
            ),
            now=now,
            deadline_at=deadline_at,
            _tracker=tracker,
        )

    async def _run_graph(
        self,
        command: BothRetrievalCommand,
        *,
        tracker: RouteAwareCallTracker,
        now: datetime,
        deadline_at: datetime,
        dependency: WorkflowDependencyBinding | None = None,
    ) -> GraphPlanningResult:
        return await self._graph.plan_and_execute(
            GraphRetrievalCommand(
                user_message=command.user_message,
                intent=command.intent,
                resolved=command.resolved,
                call_tracker=command.call_tracker,
                graph_projection_enabled=command.graph_projection_enabled,
                workflow_dependency=dependency,
            ),
            now=now,
            deadline_at=deadline_at,
            _tracker=tracker,
        )

    @staticmethod
    def _graph_event_dependency(
        command: BothRetrievalCommand,
        result: GraphPlanningResult,
    ) -> WorkflowDependencyBinding | None:
        if result.execution is None:
            return None
        values: list[str] = []
        for graph_result in result.execution.results:
            values.extend(evidence.event_id for evidence in graph_result.evidence)
            values.extend(
                relationship.last_event_id
                for relationship in graph_result.relationships
                if relationship.last_event_id is not None
            )
        values = list(dict.fromkeys(value for value in values if value))[
            : command.resolved.caps.fanout_limit
        ]
        if not values:
            return None
        return WorkflowDependencyBinding(
            opaque_reference="graph-result.event_refs",
            source_axis=WorkflowAxis.GRAPH,
            target_axis=WorkflowAxis.CANONICAL,
            kind=WorkflowDependencyKind.EVENT_REFERENCES,
            actual_values=tuple(values),
        )

    @staticmethod
    def _canonical_character_dependency(
        command: BothRetrievalCommand,
        result: CanonicalPlanningResult,
    ) -> WorkflowDependencyBinding | None:
        if result.execution is None:
            return None
        allowed = {
            command.resolved.requester_world_character_id,
            command.resolved.responding_world_character_id,
            *(binding.world_character_id for binding in command.resolved.entity_bindings),
        }
        values: list[str] = []
        for record in result.execution.records:
            if record.counterpart_world_character_id in allowed:
                values.append(record.counterpart_world_character_id)
            values.extend(value for value in record.metadata.values() if value in allowed)
        values = [
            value
            for value in dict.fromkeys(values)
            if value != command.resolved.responding_world_character_id
        ][: command.resolved.caps.fanout_limit]
        if not values:
            return None
        return WorkflowDependencyBinding(
            opaque_reference="canonical-result.world_character_refs",
            source_axis=WorkflowAxis.CANONICAL,
            target_axis=WorkflowAxis.GRAPH,
            kind=WorkflowDependencyKind.WORLD_CHARACTER_REFERENCES,
            actual_values=tuple(values),
        )

    @staticmethod
    def _downstream_reason(
        axis: WorkflowAxis,
        resolved: ResolvedRetrievalEnvelope,
        dependency: WorkflowDependencyBinding | None,
        *,
        source_result: CanonicalPlanningResult | GraphPlanningResult,
    ) -> str | None:
        if source_result.metrics.short_circuited:
            return f"upstream_{source_result.metrics.short_circuit_reason}"
        if dependency is None:
            return "workflow_dependency_empty"
        if axis is WorkflowAxis.CANONICAL:
            if not resolved.memory_enabled:
                return "canonical_memory_opt_out"
            if not resolved.canonical_operation_allowlist:
                return "canonical_operation_allowlist_empty"
        else:
            if not resolved.observable:
                return "graph_scope_unobservable"
            if not resolved.graph_operation_allowlist:
                return "graph_operation_allowlist_empty"
        return None

    @staticmethod
    def _workflow(
        command: BothRetrievalCommand,
        selection: WorkflowRecipeSelection,
        canonical: CanonicalPlanningResult | None,
        graph: GraphPlanningResult | None,
    ) -> RetrievalWorkflow | None:
        if (
            canonical is None
            or canonical.plan is None
            or graph is None
            or graph.plan is None
        ):
            return None
        return RetrievalWorkflow(
            request_id=command.resolved.request_id,
            route=RetrievalRoute.BOTH,
            envelope_version=command.resolved.version,
            envelope_hash=command.resolved.envelope_hash,
            canonical_plan=canonical.plan,
            graph_plan=graph.plan,
            recipe=selection.selected,
        )

    @classmethod
    def _merge_references(
        cls,
        command: BothRetrievalCommand,
        *,
        selection: WorkflowRecipeSelection,
        canonical: CanonicalPlanningResult | None,
        graph: GraphPlanningResult | None,
    ) -> tuple[tuple[CoordinatedRetrievalReference, ...], dict[str, int]]:
        canonical_candidates = cls._canonical_candidates(command, canonical)
        graph_candidates = cls._graph_candidates(command, graph)
        input_count = len(canonical_candidates) + len(graph_candidates)
        if selection.spec.planners_parallel:
            groups = cls._union_groups(canonical_candidates, graph_candidates)
            dropped = 0
        else:
            groups = cls._intersection_groups(
                canonical_candidates,
                graph_candidates,
                dependency_kind=selection.spec.dependency_kind,
            )
            consumed = sum(
                len(group.canonical_references) + len(group.graph_references)
                for group in groups
            )
            dropped = max(0, input_count - consumed)
        groups_before_dedupe = len(groups)
        groups = cls._deduplicate_groups(groups)
        joined = sum(
            bool(group.canonical_references and group.graph_references)
            for group in groups
        )
        references = cls._rank_groups(
            command,
            groups,
            limit=command.resolved.caps.row_limit,
        )
        return references, {
            "input": input_count,
            "joined": joined,
            "dropped": dropped,
            "deduplicated": groups_before_dedupe - len(groups),
        }

    @staticmethod
    def _canonical_candidates(
        command: BothRetrievalCommand,
        result: CanonicalPlanningResult | None,
    ) -> tuple[_AxisCandidate, ...]:
        if result is None or result.execution is None:
            return ()
        allowed_characters = {
            command.resolved.requester_world_character_id,
            command.resolved.responding_world_character_id,
            *(binding.world_character_id for binding in command.resolved.entity_bindings),
        }
        event_kinds = {
            RecallDocumentKind.SOCIAL_EVENT,
            RecallDocumentKind.ACTIVITY_EVENT,
            RecallDocumentKind.RELATIONSHIP_EVENT,
        }
        candidates: list[_AxisCandidate] = []
        for record in result.execution.records:
            event_references = list(record.evidence_references)
            if record.source_event_id is not None:
                event_references.append(record.source_event_id)
            if record.kind in event_kinds:
                event_references.append(record.canonical_source_id)
            characters = []
            if record.counterpart_world_character_id in allowed_characters:
                characters.append(record.counterpart_world_character_id)
            characters.extend(
                value for value in record.metadata.values() if value in allowed_characters
            )
            candidates.append(
                _AxisCandidate(
                    axis=WorkflowAxis.CANONICAL,
                    axis_reference=record.reference,
                    event_references=tuple(
                        sorted(dict.fromkeys(value for value in event_references if value))
                    ),
                    world_character_references=tuple(
                        sorted(dict.fromkeys(characters))
                    ),
                    occurred_at=record.occurred_at,
                )
            )
        return tuple(candidates)

    @staticmethod
    def _graph_candidates(
        command: BothRetrievalCommand,
        result: GraphPlanningResult | None,
    ) -> tuple[_AxisCandidate, ...]:
        del command
        if result is None or result.execution is None:
            return ()
        candidates: list[_AxisCandidate] = []
        for index, graph_result in enumerate(result.execution.results, start=1):
            event_references, characters, occurred_at = _graph_result_values(
                graph_result
            )
            candidates.append(
                _AxisCandidate(
                    axis=WorkflowAxis.GRAPH,
                    axis_reference=f"graph-result-{index}",
                    event_references=event_references,
                    world_character_references=characters,
                    occurred_at=occurred_at,
                )
            )
        return tuple(candidates)

    @classmethod
    def _union_groups(
        cls,
        canonical: tuple[_AxisCandidate, ...],
        graph: tuple[_AxisCandidate, ...],
    ) -> list[_CandidateGroup]:
        groups = [cls._new_group(candidate) for candidate in canonical]
        for candidate in graph:
            matching = [
                group
                for group in groups
                if cls._matches(group, candidate, require=None)
            ]
            if not matching:
                groups.append(cls._new_group(candidate))
                continue
            primary = matching[0]
            cls._add_candidate(primary, candidate)
            for duplicate in matching[1:]:
                cls._merge_group(primary, duplicate)
                groups.remove(duplicate)
        return groups

    @classmethod
    def _intersection_groups(
        cls,
        canonical: tuple[_AxisCandidate, ...],
        graph: tuple[_AxisCandidate, ...],
        *,
        dependency_kind: WorkflowDependencyKind | None,
    ) -> list[_CandidateGroup]:
        if dependency_kind is None:
            raise RetrievalContractError("retrieval_workflow_dependency_kind_missing")
        groups: list[_CandidateGroup] = []
        for canonical_candidate in canonical:
            matching = [
                graph_candidate
                for graph_candidate in graph
                if cls._candidate_match(
                    canonical_candidate,
                    graph_candidate,
                    require=dependency_kind,
                )
            ]
            if not matching:
                continue
            group = cls._new_group(canonical_candidate)
            for graph_candidate in matching:
                cls._add_candidate(group, graph_candidate)
            groups.append(group)
        return groups

    @staticmethod
    def _new_group(candidate: _AxisCandidate) -> _CandidateGroup:
        return _CandidateGroup(
            canonical_references=(
                {candidate.axis_reference}
                if candidate.axis is WorkflowAxis.CANONICAL
                else set()
            ),
            graph_references=(
                {candidate.axis_reference}
                if candidate.axis is WorkflowAxis.GRAPH
                else set()
            ),
            event_references=set(candidate.event_references),
            world_character_references=set(candidate.world_character_references),
            occurred_at=candidate.occurred_at,
        )

    @classmethod
    def _add_candidate(
        cls,
        group: _CandidateGroup,
        candidate: _AxisCandidate,
    ) -> None:
        event_match = bool(group.event_references & set(candidate.event_references))
        character_match = bool(
            group.world_character_references
            & set(candidate.world_character_references)
        )
        if candidate.axis is WorkflowAxis.CANONICAL:
            group.canonical_references.add(candidate.axis_reference)
        else:
            group.graph_references.add(candidate.axis_reference)
        group.event_references.update(candidate.event_references)
        group.world_character_references.update(candidate.world_character_references)
        group.matched_event = group.matched_event or event_match
        group.matched_world_character = (
            group.matched_world_character or character_match
        )
        group.occurred_at = _latest(group.occurred_at, candidate.occurred_at)

    @staticmethod
    def _merge_group(target: _CandidateGroup, source: _CandidateGroup) -> None:
        target.canonical_references.update(source.canonical_references)
        target.graph_references.update(source.graph_references)
        target.event_references.update(source.event_references)
        target.world_character_references.update(source.world_character_references)
        target.matched_event = target.matched_event or source.matched_event
        target.matched_world_character = (
            target.matched_world_character or source.matched_world_character
        )
        target.occurred_at = _latest(target.occurred_at, source.occurred_at)

    @classmethod
    def _matches(
        cls,
        group: _CandidateGroup,
        candidate: _AxisCandidate,
        *,
        require: WorkflowDependencyKind | None,
    ) -> bool:
        event_match = bool(group.event_references & set(candidate.event_references))
        character_match = bool(
            group.world_character_references
            & set(candidate.world_character_references)
        )
        if require is WorkflowDependencyKind.EVENT_REFERENCES:
            return event_match
        if require is WorkflowDependencyKind.WORLD_CHARACTER_REFERENCES:
            return character_match
        return event_match or character_match

    @staticmethod
    def _candidate_match(
        left: _AxisCandidate,
        right: _AxisCandidate,
        *,
        require: WorkflowDependencyKind,
    ) -> bool:
        if require is WorkflowDependencyKind.EVENT_REFERENCES:
            return bool(set(left.event_references) & set(right.event_references))
        return bool(
            set(left.world_character_references)
            & set(right.world_character_references)
        )

    @classmethod
    def _deduplicate_groups(
        cls,
        groups: list[_CandidateGroup],
    ) -> list[_CandidateGroup]:
        deduplicated: dict[tuple[Any, ...], _CandidateGroup] = {}
        for group in groups:
            if group.event_references:
                key: tuple[Any, ...] = ("event", *sorted(group.event_references))
            elif group.world_character_references:
                key = ("character", *sorted(group.world_character_references))
            else:
                key = (
                    "axis",
                    *sorted(group.canonical_references),
                    "|",
                    *sorted(group.graph_references),
                )
            existing = deduplicated.get(key)
            if existing is None:
                deduplicated[key] = group
            else:
                cls._merge_group(existing, group)
        return list(deduplicated.values())

    @staticmethod
    def _rank_groups(
        command: BothRetrievalCommand,
        groups: list[_CandidateGroup],
        *,
        limit: int,
    ) -> tuple[CoordinatedRetrievalReference, ...]:
        scored: list[tuple[int, float, str, _CandidateGroup]] = []
        for group in groups:
            score = (
                (1_000 if group.canonical_references and group.graph_references else 0)
                + (300 if group.matched_event else 0)
                + (100 if group.matched_world_character else 0)
                + min(len(group.event_references), 20) * 5
                + min(len(group.world_character_references), 20) * 2
            )
            opaque = _opaque_reference(command, group)
            occurred = (
                float("-inf")
                if group.occurred_at is None
                else group.occurred_at.timestamp()
            )
            scored.append((score, occurred, opaque, group))
        scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
        return tuple(
            CoordinatedRetrievalReference(
                opaque_reference=opaque,
                rank=index,
                score=score,
                axes=tuple(
                    axis
                    for axis, present in (
                        (WorkflowAxis.CANONICAL, bool(group.canonical_references)),
                        (WorkflowAxis.GRAPH, bool(group.graph_references)),
                    )
                    if present
                ),
                canonical_references=tuple(sorted(group.canonical_references)),
                graph_references=tuple(sorted(group.graph_references)),
                event_references=tuple(sorted(group.event_references)),
                world_character_references=tuple(
                    sorted(group.world_character_references)
                ),
            )
            for index, (score, _occurred, opaque, group) in enumerate(
                scored[:limit],
                start=1,
            )
        )


def _graph_result_values(
    result: GraphRecallResult,
) -> tuple[tuple[str, ...], tuple[str, ...], datetime | None]:
    events = [evidence.event_id for evidence in result.evidence]
    events.extend(
        relationship.last_event_id
        for relationship in result.relationships
        if relationship.last_event_id is not None
    )
    characters = list(result.world_character_ids)
    if result.path is not None:
        characters.extend(result.path.world_character_ids)
    occurred_values: list[datetime] = []
    for relationship in result.relationships:
        characters.extend(
            (
                relationship.actor_world_character_id,
                relationship.target_world_character_id,
            )
        )
        occurred_values.extend(
            value
            for value in (relationship.last_event_at, relationship.updated_at)
            if value is not None
        )
    for evidence in result.evidence:
        characters.append(evidence.actor_world_character_id)
        if evidence.target_world_character_id is not None:
            characters.append(evidence.target_world_character_id)
        occurred_values.append(evidence.occurred_at)
    return (
        tuple(sorted(dict.fromkeys(value for value in events if value))),
        tuple(sorted(dict.fromkeys(value for value in characters if value))),
        max(occurred_values) if occurred_values else None,
    )


def _latest(left: datetime | None, right: datetime | None) -> datetime | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


def _opaque_reference(
    command: BothRetrievalCommand,
    group: _CandidateGroup,
) -> str:
    payload = "\x1f".join(
        (
            command.resolved.request_id,
            command.resolved.envelope_hash,
            *sorted(group.canonical_references),
            *sorted(group.graph_references),
            *sorted(group.event_references),
            *sorted(group.world_character_references),
        )
    )
    return f"workflow-ref-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20]}"


__all__ = [
    "BothRetrievalCommand",
    "BothRetrievalResult",
    "BothRetrievalWorkflowCoordinator",
    "CoordinatedRetrievalReference",
    "WorkflowCoordinatorMetrics",
]
