"""Closed graph primitive registry and provider-free recall executor."""

from __future__ import annotations

from app.contracts.retrieval_observation import observe

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from app.domains.relationships.exceptions import (
    GraphReadBackendError,
    RelationshipGraphForbiddenError,
    RelationshipGraphNotFoundError,
    RelationshipGraphRequestError,
)
from app.domains.relationships.contracts.graph_query import (
    GraphEvidenceCandidate,
    GraphNodeCandidate,
    GraphPathHit,
    GraphRelationshipHit,
    RelationshipGraphQueryPort,
    RelationshipRevalidationFacts,
)
from app.domains.relationships.contracts.graph_read import (GraphProjectionCounts)
from app.domains.relationships.contracts.graph_recall import (
    MAX_GRAPH_RECALL_EDGES,
    MAX_GRAPH_RECALL_EVIDENCE,
    MAX_GRAPH_RECALL_HOPS,
    MAX_GRAPH_RECALL_RESULTS,
    GraphRecallDirection,
    GraphRecallEvidence,
    GraphRecallOperation,
    GraphRecallPath,
    GraphRecallQuery,
    GraphRecallRanking,
    GraphRecallRelationship,
    GraphRecallResult,
    GraphRecallScope,
    GraphRecallScopeAccess,
    GraphRecallSource,
    GraphRecallStatus,
)
from app.domains.relationships.contracts.graph_recall_gateway import (
    FallbackMode,
    GraphRecallPrimitiveSpec,
    GRAPH_RECALL_PRIMITIVE_REGISTRY,
    GraphRecallGateway,
)
from app.domains.relationships.policies.graph_recall import (
    _validate_reference,
    _result,
    _direct_orientation,
    _matches_direction,
    _ids_match_direction,
    _filter_direction,
    _evidence_matches_direction,
    _relationship_facts_valid,
    _relationship_record,
    _node_valid,
    _evidence_candidate_valid,
    _neighbor_ids,
    _path_edges_match_nodes,
    _bounded_neighborhood,
    _rank_key,
    _optional_datetime,
    _as_utc,
)


class GraphRecallValidator:
    def validate(self, query: GraphRecallQuery) -> GraphRecallQuery:
        if not isinstance(query.operation, GraphRecallOperation):
            raise RelationshipGraphRequestError("graph_recall_operation_invalid")
        if not isinstance(query.scope, GraphRecallScope):
            raise RelationshipGraphRequestError("graph_recall_scope_invalid")
        spec = GRAPH_RECALL_PRIMITIVE_REGISTRY.get(query.operation)
        if spec is None:
            raise RelationshipGraphRequestError("graph_recall_operation_unknown")
        if not isinstance(query.direction, GraphRecallDirection):
            raise RelationshipGraphRequestError("graph_recall_direction_invalid")
        if not isinstance(query.ranking, GraphRecallRanking):
            raise RelationshipGraphRequestError("graph_recall_ranking_invalid")
        _validate_reference(query.scope.owner_id, "owner")
        _validate_reference(query.scope.world_id, "world")
        _validate_reference(
            query.scope.subject_world_character_id,
            "subject_world_character",
        )
        counterpart = query.counterpart_world_character_id
        if spec.requires_counterpart:
            _validate_reference(counterpart, "counterpart_world_character")
            if counterpart == query.scope.subject_world_character_id:
                raise RelationshipGraphRequestError("graph_recall_self_target")
        elif counterpart is not None:
            raise RelationshipGraphRequestError(
                "graph_recall_counterpart_not_allowed"
            )
        if (
            type(query.limit) is not int
            or query.limit < 1
            or query.limit > spec.max_results
        ):
            raise RelationshipGraphRequestError("graph_recall_limit_invalid")
        if (
            type(query.max_hops) is not int
            or query.max_hops < 1
            or query.max_hops > MAX_GRAPH_RECALL_HOPS
        ):
            raise RelationshipGraphRequestError("graph_recall_hops_invalid")
        if type(query.depth) is not int or query.depth < 1 or query.depth > 2:
            raise RelationshipGraphRequestError("graph_recall_depth_invalid")
        return query


class GraphRecallService:
    """Execute typed graph reads; no Planner, SQL, or Cypher is accepted."""

    def __init__(
        self,
        gateway: GraphRecallGateway,
        *,
        validator: GraphRecallValidator | None = None,
    ) -> None:
        self._gateway = gateway
        self._validator = validator or GraphRecallValidator()

    def execute(
        self,
        query: GraphRecallQuery,
        *,
        graph_projection_enabled: bool = True,
        repository: RelationshipGraphQueryPort | None = None,
        now: datetime | None = None,
    ) -> GraphRecallResult:
        validated = self._validator.validate(query)
        self._validate_scope(validated)
        counts = self._gateway.projection_counts(
            world_id=validated.scope.world_id
        )
        self._record_projection_metrics(counts, now=now)
        opened_repository = False
        try:
            if repository is None and not graph_projection_enabled:
                raise GraphReadBackendError("graph_disabled")
            if counts.active_replay:
                raise GraphReadBackendError("graph_rebuilding")
            if counts.failed_rebuild:
                raise GraphReadBackendError("graph_rebuild_failed")
            if repository is None:
                repository = self._gateway.open_graph_repository()
                opened_repository = True
            observe("search", method="graph_projection", executed=True)
            result = self._execute_graph(
                validated,
                repository=repository,
                counts=counts,
            )
            observe("graph_result", candidates=result.candidate_count, excluded=result.excluded_count, status=result.status.value)
            if (
                result.candidate_count == 0
                and (counts.pending or counts.processing)
                and GRAPH_RECALL_PRIMITIVE_REGISTRY[
                    validated.operation
                ].fallback_mode
                != "none"
            ):
                return self._fallback(
                    validated,
                    reason="graph_projection_lagging",
                    status=GraphRecallStatus.LAGGING,
                )
            return result
        except GraphReadBackendError as exc:
            return self._fallback(validated, reason=exc.error_class)
        except (OSError, ValueError):
            return self._fallback(
                validated,
                reason="graph_query_invalid_result",
            )
        finally:
            if opened_repository:
                self._gateway.close_graph_repository()

    def _validate_scope(self, query: GraphRecallQuery) -> None:
        access = self._gateway.graph_recall_scope_access(scope=query.scope)
        if not access.subject_exists or access.character_deleted:
            raise RelationshipGraphNotFoundError(
                query.scope.subject_world_character_id
            )
        if access.character_owner_id != query.scope.owner_id:
            raise RelationshipGraphForbiddenError(
                query.scope.subject_world_character_id
            )
        if (
            access.subject_world_id != query.scope.world_id
            or access.membership_world_id != query.scope.world_id
        ):
            raise RelationshipGraphRequestError("world_mismatch")
        if (
            access.world_character_status != "active"
            or access.membership_status != "active"
        ):
            raise RelationshipGraphRequestError("membership_inactive")
        if query.counterpart_world_character_id is not None:
            nodes = self._valid_node_ids(
                query.scope,
                (query.counterpart_world_character_id,),
            )
            if nodes != (query.counterpart_world_character_id,):
                raise RelationshipGraphRequestError(
                    "graph_recall_counterpart_unavailable"
                )

    def _record_projection_metrics(
        self,
        counts: GraphProjectionCounts,
        *,
        now: datetime | None,
    ) -> None:
        checked_at = _as_utc(now or datetime.now(UTC))
        oldest = counts.oldest_pending_at
        if oldest is not None:
            oldest = _as_utc(oldest)
        lag = max(0.0, (checked_at - oldest).total_seconds()) if oldest else 0.0
        self._gateway.record_projection_metrics(
            pending_count=counts.pending + counts.processing,
            oldest_pending_age_seconds=lag,
        )

    def _execute_graph(
        self,
        query: GraphRecallQuery,
        *,
        repository: RelationshipGraphQueryPort,
        counts: GraphProjectionCounts,
    ) -> GraphRecallResult:
        status = (
            GraphRecallStatus.LAGGING
            if counts.pending or counts.processing
            else GraphRecallStatus.READY
        )
        if query.operation is GraphRecallOperation.DIRECT_RELATIONSHIP:
            raw = self._direct_hits(repository, query)
            accepted, excluded = self._revalidate_hits(query.scope, raw)
            accepted, direction_excluded = _filter_direction(query, accepted)
            return _result(
                query,
                status=status,
                relationships=accepted[: query.limit],
                candidate_count=len(raw),
                excluded_count=excluded + direction_excluded,
                truncated=len(accepted) >= query.limit,
            )
        if query.operation is GraphRecallOperation.RELATIONSHIP_EVIDENCE:
            raw = self._direct_hits(repository, query)
            accepted, excluded = self._revalidate_hits(query.scope, raw)
            accepted, direction_excluded = _filter_direction(query, accepted)
            event_ids, raw_evidence_count, graph_evidence_excluded = (
                self._graph_evidence_ids(
                    repository,
                    query,
                    accepted_relationships=accepted,
                )
            )
            evidence, evidence_excluded = self._revalidate_evidence(
                query,
                event_ids,
                limit=query.limit,
            )
            return _result(
                query,
                status=status,
                relationships=accepted,
                evidence=evidence,
                candidate_count=len(raw) + raw_evidence_count,
                excluded_count=(
                    excluded
                    + direction_excluded
                    + graph_evidence_excluded
                    + evidence_excluded
                ),
                truncated=len(evidence) >= query.limit,
            )
        if query.operation is GraphRecallOperation.SHARED_NEIGHBORS:
            raw_ids = repository.list_shared_neighbors(
                world_id=query.scope.world_id,
                source_world_character_id=(
                    query.scope.subject_world_character_id
                ),
                target_world_character_id=(
                    query.counterpart_world_character_id or ""
                ),
                direction_mode=query.direction.value,
                limit=query.limit,
            )
            valid_ids = self._valid_node_ids(query.scope, tuple(raw_ids))
            canonical_ids = self._canonical_shared_neighbor_ids(query)
            accepted_ids = tuple(
                value
                for value in valid_ids
                if value in canonical_ids
            )[: query.limit]
            return _result(
                query,
                status=status,
                world_character_ids=accepted_ids,
                candidate_count=len(raw_ids),
                excluded_count=max(0, len(raw_ids) - len(accepted_ids)),
                truncated=len(raw_ids) >= query.limit,
            )
        if query.operation is GraphRecallOperation.SHORTEST_PATH:
            raw_path = repository.find_shortest_path(
                world_id=query.scope.world_id,
                source_world_character_id=(
                    query.scope.subject_world_character_id
                ),
                target_world_character_id=(
                    query.counterpart_world_character_id or ""
                ),
                direction_mode=query.direction.value,
                max_hops=query.max_hops,
            )
            path, candidate_count, excluded = self._revalidate_path(
                query,
                raw_path,
            )
            return _result(
                query,
                status=status,
                path=path,
                world_character_ids=(
                    path.world_character_ids if path is not None else ()
                ),
                relationships=(
                    path.relationships if path is not None else ()
                ),
                candidate_count=candidate_count,
                excluded_count=excluded,
            )
        if query.operation is GraphRecallOperation.RANK_RELATED_CHARACTERS:
            raw = repository.rank_related_characters(
                world_id=query.scope.world_id,
                source_world_character_id=(
                    query.scope.subject_world_character_id
                ),
                mode=query.ranking.value,
                limit=query.limit,
            )
            accepted, excluded = self._revalidate_hits(query.scope, raw)
            accepted = tuple(
                value
                for value in accepted
                if value.actor_world_character_id
                == query.scope.subject_world_character_id
            )
            return _result(
                query,
                status=status,
                relationships=accepted[: query.limit],
                world_character_ids=tuple(
                    value.target_world_character_id
                    for value in accepted[: query.limit]
                ),
                candidate_count=len(raw),
                excluded_count=max(excluded, len(raw) - len(accepted)),
                truncated=len(accepted) >= query.limit,
            )
        neighborhood = repository.get_visualization_neighborhood(
            world_id=query.scope.world_id,
            source_world_character_id=query.scope.subject_world_character_id,
            depth=query.depth,
            node_limit=query.limit,
            edge_limit=min(MAX_GRAPH_RECALL_EDGES, query.limit * 2),
        )
        accepted, excluded = self._revalidate_hits(
            query.scope,
            list(neighborhood.edges),
        )
        valid_nodes = set(
            self._valid_node_ids(query.scope, neighborhood.nodes)
        )
        accepted = tuple(
            value
            for value in accepted
            if value.actor_world_character_id in valid_nodes
            and value.target_world_character_id in valid_nodes
        )
        accepted, used_nodes = _bounded_neighborhood(
            query.scope.subject_world_character_id,
            accepted,
            depth=query.depth,
        )
        return _result(
            query,
            status=status,
            relationships=accepted,
            world_character_ids=tuple(sorted(used_nodes))[: query.limit],
            candidate_count=len(neighborhood.edges),
            excluded_count=max(
                excluded,
                len(neighborhood.edges) - len(accepted),
            ),
            truncated=neighborhood.truncated,
        )

    def _fallback(
        self,
        query: GraphRecallQuery,
        *,
        reason: str,
        status: GraphRecallStatus = GraphRecallStatus.DEGRADED,
    ) -> GraphRecallResult:
        self._gateway.record_fallback(reason=reason)
        mode = GRAPH_RECALL_PRIMITIVE_REGISTRY[query.operation].fallback_mode
        observe("search", method="graph_canonical_fallback", reason=reason, executed=mode != "none", skipped=mode == "none")
        if mode == "none":
            return GraphRecallResult(
                operation=query.operation,
                status=status,
                source=GraphRecallSource.NONE,
                reason_code=reason,
            )
        if mode == "shared":
            shared_ids = self._canonical_shared_neighbor_ids(query)
            return GraphRecallResult(
                operation=query.operation,
                status=status,
                source=GraphRecallSource.CANONICAL_FALLBACK,
                world_character_ids=shared_ids[: query.limit],
                candidate_count=len(shared_ids),
                truncated=len(shared_ids) >= query.limit,
                reason_code=reason,
            )
        raw = self._canonical_direct_hits(query)
        accepted, excluded = self._revalidate_hits(query.scope, raw)
        if mode == "rank":
            accepted = tuple(
                sorted(
                    (
                        value
                        for value in accepted
                        if value.actor_world_character_id
                        == query.scope.subject_world_character_id
                    ),
                    key=lambda value: _rank_key(value, query.ranking),
                    reverse=True,
                )
            )
            return GraphRecallResult(
                operation=query.operation,
                status=status,
                source=GraphRecallSource.CANONICAL_FALLBACK,
                relationships=accepted[: query.limit],
                world_character_ids=tuple(
                    value.target_world_character_id
                    for value in accepted[: query.limit]
                ),
                candidate_count=len(raw),
                excluded_count=excluded,
                truncated=len(accepted) >= query.limit,
                reason_code=reason,
            )
        evidence: tuple[GraphRecallEvidence, ...] = ()
        evidence_excluded = 0
        evidence_candidate_count = 0
        if mode == "evidence":
            event_ids = tuple(
                dict.fromkeys(
                    value.last_event_id
                    for value in accepted
                    if value.last_event_id is not None
                )
            )
            evidence_candidate_count = len(event_ids)
            evidence, evidence_excluded = self._revalidate_evidence(
                query,
                event_ids,
                limit=query.limit,
            )
        return GraphRecallResult(
            operation=query.operation,
            status=status,
            source=GraphRecallSource.CANONICAL_FALLBACK,
            relationships=accepted[: query.limit],
            evidence=evidence,
            candidate_count=len(raw) + evidence_candidate_count,
            excluded_count=excluded + evidence_excluded,
            truncated=len(accepted) >= query.limit,
            reason_code=reason,
        )

    def _direct_hits(
        self,
        repository: RelationshipGraphQueryPort,
        query: GraphRecallQuery,
    ) -> list[GraphRelationshipHit]:
        source_id, target_id, include_reverse = _direct_orientation(query)
        return repository.get_direct_relationship(
            world_id=query.scope.world_id,
            source_world_character_id=source_id,
            target_world_character_id=target_id,
            include_reverse=include_reverse,
        )

    def _graph_evidence_ids(
        self,
        repository: RelationshipGraphQueryPort,
        query: GraphRecallQuery,
        *,
        accepted_relationships: tuple[GraphRecallRelationship, ...],
    ) -> tuple[tuple[str, ...], int, int]:
        source_id, target_id, include_reverse = _direct_orientation(query)
        pairs = [(source_id, target_id)]
        if include_reverse:
            pairs.append((target_id, source_id))
        allowed_states = {
            value.relationship_state_id: value.relationship_version
            for value in accepted_relationships
        }
        event_ids: list[str] = []
        raw_count = 0
        excluded = 0
        for pair_source, pair_target in pairs:
            hits = repository.list_relationship_evidence(
                world_id=query.scope.world_id,
                source_world_character_id=pair_source,
                target_world_character_id=pair_target,
                limit=query.limit,
            )
            raw_count += len(hits)
            for value in hits:
                current_version = allowed_states.get(
                    value.relationship_state_id
                )
                if (
                    current_version is None
                    or value.relationship_version < 1
                    or value.relationship_version > current_version
                ):
                    excluded += 1
                    continue
                event_ids.append(value.event_id)
        bounded = tuple(dict.fromkeys(event_ids))[: query.limit]
        return bounded, raw_count, excluded

    def _canonical_direct_hits(
        self,
        query: GraphRecallQuery,
    ) -> list[GraphRelationshipHit]:
        raw = self._gateway.canonical_direct_hits(
            world_id=query.scope.world_id,
            center_id=query.scope.subject_world_character_id,
            target_id=query.counterpart_world_character_id,
            limit=min(MAX_GRAPH_RECALL_EDGES, query.limit * 2),
        )
        return [value for value in raw if _matches_direction(query, value)]

    def _canonical_shared_neighbor_ids(
        self,
        query: GraphRecallQuery,
    ) -> tuple[str, ...]:
        counterpart_id = query.counterpart_world_character_id
        if counterpart_id is None:
            return ()
        subject_hits = self._gateway.canonical_direct_hits(
            world_id=query.scope.world_id,
            center_id=query.scope.subject_world_character_id,
            target_id=None,
            limit=MAX_GRAPH_RECALL_EDGES,
        )
        counterpart_hits = self._gateway.canonical_direct_hits(
            world_id=query.scope.world_id,
            center_id=counterpart_id,
            target_id=None,
            limit=MAX_GRAPH_RECALL_EDGES,
        )
        subject_valid, _ = self._revalidate_hits(query.scope, subject_hits)
        counterpart_valid, _ = self._revalidate_hits(
            query.scope,
            counterpart_hits,
        )
        subject_neighbors = _neighbor_ids(
            query.scope.subject_world_character_id,
            subject_valid,
            query.direction,
        )
        counterpart_neighbors = _neighbor_ids(
            counterpart_id,
            counterpart_valid,
            query.direction,
        )
        shared = subject_neighbors & counterpart_neighbors
        shared.discard(query.scope.subject_world_character_id)
        shared.discard(counterpart_id)
        return self._valid_node_ids(query.scope, tuple(sorted(shared)))

    def _revalidate_hits(
        self,
        scope: GraphRecallScope,
        hits: list[GraphRelationshipHit],
    ) -> tuple[tuple[GraphRecallRelationship, ...], int]:
        if not hits:
            return (), 0
        facts_by_state = self._gateway.relationship_revalidation_facts(
            world_id=scope.world_id,
            hits=hits,
            subject_world_character_id=scope.subject_world_character_id,
        )
        accepted: list[GraphRecallRelationship] = []
        excluded = 0
        for hit in hits:
            facts = facts_by_state.get(hit.relationship_state_id)
            canonical = facts.canonical_hit if facts is not None else None
            if not _relationship_facts_valid(
                scope,
                hit,
                facts,
                canonical,
            ):
                excluded += 1
                continue
            assert canonical is not None
            selected = hit
            if canonical.relationship_version != hit.relationship_version:
                self._gateway.record_stale_edge()
                selected = canonical
            accepted.append(_relationship_record(selected))
        return tuple(accepted), excluded

    def _valid_node_ids(
        self,
        scope: GraphRecallScope,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        ordered = tuple(dict.fromkeys(values))
        if not ordered:
            return ()
        candidates = {
            value.world_character_id: value
            for value in self._gateway.node_candidates(
                world_id=scope.world_id,
                world_character_ids=set(ordered),
                subject_world_character_id=(
                    scope.subject_world_character_id
                ),
            )
        }
        return tuple(
            value
            for value in ordered
            if _node_valid(scope, candidates.get(value))
        )

    def _revalidate_path(
        self,
        query: GraphRecallQuery,
        path: GraphPathHit | None,
    ) -> tuple[GraphRecallPath | None, int, int]:
        if path is None:
            return None, 0, 0
        candidate_count = len(path.oriented_edges)
        if (
            path.hop_count < 1
            or path.hop_count > query.max_hops
            or len(path.oriented_edges) != path.hop_count
            or len(path.world_character_ids) != path.hop_count + 1
            or path.world_character_ids[0]
            != query.scope.subject_world_character_id
            or path.world_character_ids[-1]
            != query.counterpart_world_character_id
            or not _path_edges_match_nodes(query, path)
        ):
            return None, candidate_count, max(1, candidate_count)
        valid_nodes = self._valid_node_ids(
            query.scope,
            path.world_character_ids,
        )
        accepted, excluded = self._revalidate_hits(
            query.scope,
            list(path.oriented_edges),
        )
        if (
            valid_nodes != path.world_character_ids
            or len(accepted) != len(path.oriented_edges)
        ):
            return None, candidate_count, max(1, excluded)
        return (
            GraphRecallPath(
                world_character_ids=path.world_character_ids,
                relationships=accepted,
                hop_count=path.hop_count,
            ),
            candidate_count,
            excluded,
        )

    def _revalidate_evidence(
        self,
        query: GraphRecallQuery,
        event_ids: tuple[str, ...],
        *,
        limit: int,
    ) -> tuple[tuple[GraphRecallEvidence, ...], int]:
        if not event_ids:
            return (), 0
        scope = query.scope
        candidates = {
            value.event_id: value
            for value in self._gateway.evidence_candidates(
                world_id=scope.world_id,
                event_ids=list(event_ids),
                subject_world_character_id=(
                    scope.subject_world_character_id
                ),
            )
        }
        accepted: list[GraphRecallEvidence] = []
        excluded = 0
        for event_id in event_ids:
            candidate = candidates.get(event_id)
            if (
                not _evidence_candidate_valid(scope, candidate)
                or not _evidence_matches_direction(query, candidate)
            ):
                excluded += 1
                continue
            assert candidate is not None
            root_post_id = None
            source_post_id = None
            for post in candidate.posts:
                root_post_id = root_post_id or post.root_post_id
                source_post_id = (
                    source_post_id or post.source_post_id or post.post_id
                )
            accepted.append(
                GraphRecallEvidence(
                    event_id=candidate.event_id,
                    event_type=candidate.event_type,
                    occurred_at=_as_utc(candidate.occurred_at),
                    actor_world_character_id=(
                        candidate.actor_world_character_id
                    ),
                    target_world_character_id=(
                        candidate.target_world_character_id
                    ),
                    root_post_id=root_post_id,
                    source_post_id=source_post_id,
                )
            )
            if len(accepted) >= limit:
                break
        return tuple(accepted), excluded


__all__ = [
    "GRAPH_RECALL_PRIMITIVE_REGISTRY",
    "GraphRecallGateway",
    "GraphRecallPrimitiveSpec",
    "GraphRecallService",
    "GraphRecallValidator",
]
