"""End-to-end P8-L-P response generation orchestration."""

from __future__ import annotations
from app.contracts.search_diagnostics import evidence_lineage

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from app.contracts.retrieval_observation import observe
from app.domains.chat.contracts.character_response_generator import (
    CharacterResponseGeneratorRequest,
)
from app.domains.chat.contracts.situation_memory import ChatSituationMemoryPort
from app.domains.chat.contracts.evidence_bundle import EvidenceKind
from app.domains.chat.contracts.recall_mode import ChatRecallMode
from app.domains.chat.contracts.generation_lifecycle import (
    TERMINAL_STATES,
    GenerationContractError,
    ResponseRequestState,
)
from app.domains.chat.contracts.response_execution import (
    ResponseAction,
    ResponseExecutionError,
    ResponseGraphState,
    ResponsePhase,
    ResponseWorkflowCommand,
)
from app.domains.chat.contracts.response_request import ResponseRequestRecord
from app.domains.chat.contracts.retrieval_intent import RetrievalContractError, RetrievalRoute
from app.domains.chat.contracts.today_sns_activity import TodaySnsSnapshotValidatorPort
from app.domains.chat.policies import select_response_action, BRANCH_ACTIONS
from app.domains.chat.service.both_retrieval import (
    BothRetrievalCommand,
    BothRetrievalWorkflowCoordinator,
)
from app.domains.chat.service.canonical_retrieval import (
    CanonicalRetrievalCommand,
    CanonicalRetrievalPlanningService,
)
from app.domains.chat.service.character_response import (
    CharacterResponseGenerationService,
)
from app.domains.chat.service.evidence_assembly import EvidenceBundleAssembler
from app.domains.chat.service.graph_retrieval import (
    GraphRetrievalCommand,
    GraphRetrievalPlanningService,
)
from app.domains.chat.service.retrieval_routing import RetrievalRoutingService


@dataclass(slots=True)
class ResponseExecutionProgress:
    record: ResponseRequestRecord
    call_tracker: dict | None = None


class ResponseWorkflowSteps:
    """One request's workers and latest durable state, never graph-global."""

    def __init__(
        self,
        *,
        command: ResponseWorkflowCommand,
        progress: ResponseExecutionProgress,
        save_transition: Callable[..., ResponseRequestRecord],
        router: RetrievalRoutingService,
        canonical: CanonicalRetrievalPlanningService,
        graph: GraphRetrievalPlanningService,
        both: BothRetrievalWorkflowCoordinator,
        evidence: EvidenceBundleAssembler,
        character_response: CharacterResponseGenerationService,
        today_snapshot_validator: TodaySnsSnapshotValidatorPort | None = None,
        social_context_provider=None,
        thought_finalizer=None,
        situation_memory: ChatSituationMemoryPort | None = None,
    ) -> None:
        self.command = command
        self.progress = progress
        self._save_transition = save_transition
        self._phase = ResponsePhase.ROUTE
        self._last_action = None
        self._started: set[ResponseAction] = set()
        self._results = {
            "routing": None,
            "bundle": None,
            "response": None,
            "workflow_recipe": None,
        }
        self._router = router
        self._canonical = canonical
        self._graph = graph
        self._both = both
        self._evidence = evidence
        self._character_response = character_response
        self._today_snapshot_validator = today_snapshot_validator
        self._social_context_provider = social_context_provider
        self._thought_finalizer = thought_finalizer
        self._situation_memory = situation_memory

    def assert_active(self, state: ResponseGraphState) -> None:
        record = self.progress.record
        if record.cancel_requested_at is not None:
            raise asyncio.CancelledError()
        if (
            state.get("request_id") != record.request_id
            or state.get("request_scope_hash") != record.request_scope_hash
            or state.get("phase") is not self._phase
            or any(state.get(key) is not value for key, value in self._results.items())
        ):
            raise ResponseExecutionError("chat_supervisor_invalid_state")
        now = datetime.now(UTC)
        if record.deadline_at <= now:
            raise RetrievalContractError("response_workflow_deadline_exceeded")
        if record.state in TERMINAL_STATES or (
            record.lease_expires_at is not None and record.lease_expires_at <= now
        ):
            raise GenerationContractError("response_workflow_lease_unavailable")

    async def execute(
        self, action: ResponseAction, state: ResponseGraphState
    ) -> ResponseGraphState:
        self.assert_active(state)
        if not self.command.recall_mode.graph_tools_enabled and action in {ResponseAction.GRAPH, ResponseAction.BOTH}:
            raise RetrievalContractError("chat_graph_capability_disabled")
        before = {**state, "visits": state["visits"] - 1, "action": self._last_action}
        expected = select_response_action(before)
        if (
            action is not expected
            or state["action"] is not action
            or action in self._started
        ):
            raise ResponseExecutionError("chat_supervisor_unknown_action")
        handlers = {
            ResponseAction.ROUTE: self.route_and_resolve,
            ResponseAction.CURRENT: self.current_context,
            ResponseAction.CANONICAL: self.canonical_retrieval,
            ResponseAction.GRAPH: self.graph_retrieval,
            ResponseAction.BOTH: self.both_retrieval,
            ResponseAction.CLARIFY: self.clarification,
            ResponseAction.FREEZE: self.freeze_evidence,
            ResponseAction.GENERATE: self.generate_response,
        }
        handler = handlers.get(action)
        if handler is None:
            raise ResponseExecutionError("chat_supervisor_unknown_action")
        self._started.add(action)
        result = await handler(state)
        select_response_action(result)
        self._phase = result["phase"]
        self._last_action = action
        self._results = {key: result[key] for key in self._results}
        return result

    def assert_finished(self, state: ResponseGraphState) -> None:
        self.assert_active(state)
        if (
            self._phase is not ResponsePhase.COMPLETE
            or state.get("action") is not ResponseAction.END
            or state.get("visits") != len(ResponsePhase)
            or self._started != {ResponseAction.ROUTE, BRANCH_ACTIONS[state["routing"].intent.route], ResponseAction.FREEZE, ResponseAction.GENERATE}
        ):
            raise ResponseExecutionError("chat_supervisor_invalid_state")

    def _transition(self, record, target, **values):
        if values.get("call_tracker") is not None:
            # Preserve attempted calls even if the following commit fails.
            self.progress.call_tracker = values["call_tracker"]
        updated = self._save_transition(record, target, **values)
        self.progress.record = updated
        return updated

    async def route_and_resolve(self, state: ResponseGraphState) -> ResponseGraphState:
        command = self.command
        record = self.progress.record
        from app.domains.chat.contracts.supervisor_selection import read_selection_protocol
        protocol = read_selection_protocol(record.node_state)
        identity_state = {}
        if command.chat_identity is not None:
            from app.domains.chat.contracts.chat_identity_context import IDENTITY_KEY
            if command.today_sns_snapshot is not None:
                retained = {entry["ref"] for entry in command.today_sns_snapshot.router_view()["entries"]}
                ids = tuple(dict.fromkeys(identifier for entry in command.today_sns_snapshot.entries if entry.opaque_reference in retained for identifier in
                    (entry.actor_id, entry.counterpart_id) if identifier and identifier not in command.chat_identity.names))
                labels = {key: value for key, value in command.character_labels.items() if key in ids}
                command = replace(command, chat_identity=command.chat_identity.extend(labels))
                self.command = command
            identity_state[IDENTITY_KEY] = command.chat_identity.to_dict()
        record = self._transition(record, ResponseRequestState.PREFLIGHTED, node_state=identity_state)
        record = self._transition(record, ResponseRequestState.ROUTING)
        routing = await self._router.route(
            command.preflight,
            recent_context=command.router_context,
            **({"social_snapshot": command.social_snapshot} if command.social_snapshot is not None else {}),
            **({"chat_identity": command.chat_identity} if command.chat_identity is not None else {}),
            **({"selection_protocol": protocol} if protocol is not None else {}),
            today_sns_context=(
                None
                if command.today_sns_snapshot is None
                else command.today_sns_snapshot.router_view()
            ),
            now=datetime.now(UTC),
            deadline_at=record.deadline_at,
        )
        record = self._transition(
            record,
            ResponseRequestState.RESOLVING,
            route=routing.intent.route,
            node_state={
                "intent_hash": routing.intent.envelope_hash,
                "resolved_hash": routing.resolved.envelope_hash,
                "recall_mode": command.recall_mode.value,
                "recall_capability_fingerprint": command.recall_mode.fingerprint,
                "social_snapshot": None if command.social_snapshot is None else command.social_snapshot.manifest(),
                "router_metrics": _safe_metrics(routing.metrics),
                "recall_interpretation": None if routing.interpretation is None else routing.interpretation.manifest(),
            },
            call_tracker=routing.call_tracker,
        )

        route = routing.intent.route
        if not command.recall_mode.graph_tools_enabled and route in {RetrievalRoute.GRAPH, RetrievalRoute.BOTH}:
            raise RetrievalContractError("chat_graph_capability_disabled")
        observe(
            "router",
            route=route.value,
            repair_used=routing.metrics.repair_used,
            first_pass_valid=routing.metrics.first_pass_valid,
        )
        return {**state, "phase": ResponsePhase.BRANCH, "routing": routing}

    async def current_context(self, state: ResponseGraphState) -> ResponseGraphState:
        record = self.progress.record
        routing = state["routing"]
        workflow_recipe = state["workflow_recipe"]
        record = self._transition(
            record,
            ResponseRequestState.CURRENT_CONTEXT_READY,
        )
        bundle = self._evidence.current_context(
            request_id=record.request_id,
            request_scope_hash=record.request_scope_hash,
        )
        tracker = routing.call_tracker
        self.progress.call_tracker = tracker
        return {
            **state,
            "phase": ResponsePhase.EVIDENCE,
            "bundle": bundle,
            "workflow_recipe": workflow_recipe,
        }

    async def clarification(self, state: ResponseGraphState) -> ResponseGraphState:
        record = self.progress.record
        routing = state["routing"]
        workflow_recipe = state["workflow_recipe"]
        record = self._transition(
            record,
            ResponseRequestState.CLARIFICATION_PREPARED,
        )
        clarification = routing.clarification
        if clarification is None:
            raise RetrievalContractError("response_clarification_missing")
        bundle = self._evidence.clarification(
            request_id=record.request_id,
            request_scope_hash=record.request_scope_hash,
            slot=clarification.slot,
        )
        tracker = routing.call_tracker
        self.progress.call_tracker = tracker
        return {
            **state,
            "phase": ResponsePhase.EVIDENCE,
            "bundle": bundle,
            "workflow_recipe": workflow_recipe,
        }

    async def canonical_retrieval(
        self, state: ResponseGraphState
    ) -> ResponseGraphState:
        command = self.command
        record = self.progress.record
        routing = state["routing"]
        workflow_recipe = state["workflow_recipe"]
        record = self._transition(
            record,
            ResponseRequestState.CANONICAL_PLANNING,
        )
        result = await self._canonical.plan_and_execute(
            CanonicalRetrievalCommand(
                user_message=command.preflight.user_message,
                image_context=command.preflight.image_context,
                chat_identity=command.chat_identity,
                thread_id=record.thread_id,
                intent=routing.intent,
                resolved=routing.resolved,
                call_tracker=routing.call_tracker,
            ),
            now=datetime.now(UTC),
            deadline_at=record.deadline_at,
        )
        record = self._transition(
            record,
            ResponseRequestState.OPTIONAL_RETRIEVING,
            node_state={"canonical_metrics": _safe_metrics(result.metrics)},
            call_tracker=result.call_tracker,
        )
        bundle = self._evidence.canonical(
            request_scope_hash=record.request_scope_hash,
            result=result,
        )
        tracker = result.call_tracker
        self.progress.call_tracker = tracker
        return {
            **state,
            "phase": ResponsePhase.EVIDENCE,
            "bundle": bundle,
            "workflow_recipe": workflow_recipe,
        }

    async def graph_retrieval(self, state: ResponseGraphState) -> ResponseGraphState:
        command = self.command
        record = self.progress.record
        routing = state["routing"]
        workflow_recipe = state["workflow_recipe"]
        record = self._transition(
            record,
            ResponseRequestState.GRAPH_PLANNING,
        )
        result = await self._graph.plan_and_execute(
            GraphRetrievalCommand(
                user_message=command.preflight.user_message,
                image_context=command.preflight.image_context,
                chat_identity=command.chat_identity,
                intent=routing.intent,
                resolved=routing.resolved,
                call_tracker=routing.call_tracker,
                graph_projection_enabled=command.graph_projection_enabled,
            ),
            now=datetime.now(UTC),
            deadline_at=record.deadline_at,
        )
        record = self._transition(
            record,
            ResponseRequestState.OPTIONAL_RETRIEVING,
            node_state={"graph_metrics": _safe_metrics(result.metrics)},
            call_tracker=result.call_tracker,
        )
        command = self._bind_graph_names(command, result)
        bundle = self._evidence.graph(
            request_scope_hash=record.request_scope_hash,
            result=result,
            character_labels=command.character_labels,
        )
        tracker = result.call_tracker
        self.progress.call_tracker = tracker
        return {
            **state,
            "phase": ResponsePhase.EVIDENCE,
            "bundle": bundle,
            "workflow_recipe": workflow_recipe,
        }

    async def both_retrieval(self, state: ResponseGraphState) -> ResponseGraphState:
        command = self.command
        record = self.progress.record
        routing = state["routing"]
        workflow_recipe = state["workflow_recipe"]
        record = self._transition(
            record,
            ResponseRequestState.BOTH_COORDINATING,
        )
        result = await self._both.coordinate(
            BothRetrievalCommand(
                user_message=command.preflight.user_message,
                image_context=command.preflight.image_context,
                chat_identity=command.chat_identity,
                thread_id=record.thread_id,
                intent=routing.intent,
                resolved=routing.resolved,
                call_tracker=routing.call_tracker,
                graph_projection_enabled=command.graph_projection_enabled,
            ),
            now=datetime.now(UTC),
            deadline_at=record.deadline_at,
        )
        workflow_recipe = result.selection.selected
        record = self._transition(
            record,
            ResponseRequestState.OPTIONAL_RETRIEVING,
            workflow_recipe=workflow_recipe,
            node_state={
                "both_metrics": _safe_metrics(result.metrics),
                **(
                    {"canonical_metrics": _safe_metrics(result.canonical.metrics)}
                    if result.canonical is not None
                    else {}
                ),
                **(
                    {"graph_metrics": _safe_metrics(result.graph.metrics)}
                    if result.graph is not None
                    else {}
                ),
            },
            call_tracker=result.call_tracker,
        )
        command = self._bind_graph_names(command, result.graph)
        bundle = self._evidence.both(
            request_scope_hash=record.request_scope_hash,
            result=result,
            character_labels=command.character_labels,
        )
        tracker = result.call_tracker

        self.progress.call_tracker = tracker
        return {
            **state,
            "phase": ResponsePhase.EVIDENCE,
            "bundle": bundle,
            "workflow_recipe": workflow_recipe,
        }

    async def freeze_evidence(self, state: ResponseGraphState) -> ResponseGraphState:
        command = self.command
        record = self.progress.record
        state["routing"]
        workflow_recipe = state["workflow_recipe"]
        bundle = state["bundle"]
        tracker = self.progress.call_tracker
        if command.social_snapshot is not None:
            self._social_context_provider.assert_current(command.social_snapshot)
        if (
            command.today_sns_snapshot is not None
            and self._today_snapshot_validator is not None
        ):
            self._today_snapshot_validator.assert_current(command.today_sns_snapshot)
        bundle = self._evidence.with_today_sns(
            bundle,
            command.today_sns_snapshot,
            user_message=command.preflight.user_message,
        )
        bundle = self._evidence.with_image(bundle, command.image_evidence)
        evidence_lineage("freeze", bundle.items)
        record = self._transition(
            record,
            ResponseRequestState.EVIDENCE_FROZEN,
            workflow_recipe=workflow_recipe,
            node_state={
                "evidence_version": bundle.version,
                "evidence_hash": bundle.evidence_hash,
                "retrieval_outcome": bundle.retrieval_outcome.value,
                "public_evidence_count": bundle.public_evidence_count,
                "today_sns_snapshot": (
                    None
                    if command.today_sns_snapshot is None
                    else {
                        "version": command.today_sns_snapshot.version,
                        "snapshot_hash": command.today_sns_snapshot.snapshot_hash,
                        "complete_through": (
                            command.today_sns_snapshot.complete_through.isoformat()
                        ),
                        "overflow": command.today_sns_snapshot.overflow,
                        "coverage": {
                            key: value.value
                            for key, value in sorted(
                                command.today_sns_snapshot.coverage.items()
                            )
                        },
                    }
                ),
            },
            call_tracker=tracker,
        )
        return {**state, "phase": ResponsePhase.RESPONSE, "bundle": bundle}

    async def generate_response(self, state: ResponseGraphState) -> ResponseGraphState:
        command = self.command
        record = self.progress.record
        routing = state["routing"]
        state["workflow_recipe"]
        bundle = state["bundle"]
        tracker = self.progress.call_tracker
        tracker = self._character_response.reserve_call(
            call_tracker=tracker,
            now=datetime.now(UTC),
            deadline_at=record.deadline_at,
        )
        candidates = ()
        interpretation = None
        response_state = {}
        if command.chat_identity is not None:
            from app.domains.chat.contracts.chat_identity_context import IDENTITY_KEY
            identifiers = tuple(dict.fromkeys(identifier for item in bundle.items
                for _, identifier in item.author_identities if identifier not in command.chat_identity.names))
            labels = command.identity_labels(identifiers) if identifiers and command.identity_labels else {}
            identity = command.chat_identity.extend(labels)
            command = replace(command, chat_identity=identity)
            self.command = command
            response_state[IDENTITY_KEY] = identity.to_dict()
        if command.recall_mode is ChatRecallMode.SOCIAL_HYBRID:
            if routing.interpretation is None:
                raise RetrievalContractError("hybrid_interpretation_missing")
            interpretation = routing.interpretation.freeze(bundle)
            counts = tracker["logical_counts"]
            if (counts["canonical_planner"] or counts["graph_planner"]
                or counts["character_response_generator"] != 1
                or counts["retrieval_router"] not in (1, 2)
                or (counts["retrieval_router"] == 2 and tracker["repair_node"] != "retrieval_router")):
                raise RetrievalContractError("hybrid_generation_budget_exceeded")
            response_state.update({"recall_interpretation": interpretation.manifest(),
                "hybrid_normal_generation_calls": 2, "final_response_kind": None}
            )
        record = self._transition(record, ResponseRequestState.RESPONSE_GENERATING,
            call_tracker=tracker, node_state=response_state)
        if routing.clarification is not None:
            candidates = tuple(
                f"{candidate.display_name} (@{candidate.handle})"
                for candidate in routing.clarification.candidates
            )
        observe("crg_input", items=len(bundle.items), route=bundle.route.value)
        evidence_lineage("crg", bundle.items)
        if command.social_snapshot is not None:
            observe("social_context_consumed", source="crg", snapshot_id="s-"+command.social_snapshot.snapshot_id,
                    content_hash="h-"+command.social_snapshot.content_hash, status=command.social_snapshot.status)
        for kind in {item.kind for item in bundle.items}:
            observe(
                "evidence_kind",
                source=kind.value,
                items=sum(item.kind is kind for item in bundle.items),
            )
        from app.contracts.activity_situation import admitted_locale
        situation = admitted_locale(command.request.node_state.get("_situation_policy"))
        if situation is not None and self._situation_memory is None:
            raise RetrievalContractError("situation_memory_runtime_missing")
        response = await self._character_response.generate(
            CharacterResponseGeneratorRequest(
                user_message=command.preflight.user_message,
                profile=command.profile,
                social_snapshot=command.social_snapshot,
                recent_context=command.response_context,
                evidence=bundle,
                clarification_candidates=candidates,
                recall_mode=command.recall_mode,
                recall_interpretation=interpretation,
                thought_finalizer=self._thought_finalizer,
                situation_locale=situation,
                chat_identity=command.chat_identity,
                situation_target=command.request.response_slot_id if situation else None,
                situation_manifest_factory=(lambda payload: self._situation_memory.freeze(command, bundle, payload)) if situation else None,
                relationship_delivery_factory=self._relationship_delivery_factory(command, bundle),
                today_sns_manifest=(
                    None
                    if command.today_sns_snapshot is None
                    else command.today_sns_snapshot.response_manifest(
                        included_references=tuple(
                            item.opaque_reference
                            for item in bundle.items
                            if item.kind is EvidenceKind.TODAY_SNS_ACTIVITY
                        )
                    )
                ),
            ),
            call_tracker=tracker,
            now=datetime.now(UTC),
            deadline_at=record.deadline_at,
        )
        observe(
            "crg_completed",
            status="completed",
            input_tokens=response.prompt_token_count,
            output_tokens=response.output_token_count,
            thought_tokens=response.thought_token_count,
            elapsed_ms=response.latency_ms,
        )
        self.progress.call_tracker = response.call_tracker
        return {**state, "phase": ResponsePhase.COMPLETE, "response": response}

    def _bind_graph_names(self, command, result):
        if command.chat_identity is None or result is None or result.execution is None:
            return command
        identifiers = set()
        for graph in result.execution.results:
            for relation in graph.relationships:
                identifiers.update((relation.actor_world_character_id, relation.target_world_character_id))
            for event in graph.evidence:
                identifiers.update((event.actor_world_character_id, event.target_world_character_id))
        identifiers.discard(None)
        unresolved = tuple(sorted(identifiers - command.chat_identity.names.keys()))
        labels = command.identity_labels(unresolved) if unresolved and command.identity_labels else {}
        identity = command.chat_identity.extend(labels)
        command = replace(command, chat_identity=identity, character_labels={**command.character_labels, **identity.names})
        self.command = command
        return command

    @staticmethod
    def _relationship_delivery_factory(command, bundle):
        from app.domains.chat.contracts.relationship_evidence import RelationshipEvidenceBinding
        from app.domains.chat.relationship_evidence_policy import capture_delivery
        from app.domains.chat.service.social_context_inspector import social_context_inspector
        binding = RelationshipEvidenceBinding.for_request(command.request,
            owner_id=command.preflight.owner_id, world_id=command.preflight.world_id,
            actor_id=command.preflight.responding_world_character_id,
            requester_id=command.preflight.requester_world_character_id)
        return lambda payload, prompt: capture_delivery(binding, bundle, command.social_snapshot,
            payload, prompt, command.chat_identity, social_context_inspector(command.social_snapshot))


def _safe_metrics(value: Any) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key in getattr(value, "__dataclass_fields__", {}):
        item = getattr(value, key)
        if isinstance(item, (str, int, float, bool)) or item is None:
            output[key] = item.value if hasattr(item, "value") else item
        elif isinstance(item, tuple):
            output[key] = [
                entry.value if hasattr(entry, "value") else entry for entry in item
            ]
    return output
