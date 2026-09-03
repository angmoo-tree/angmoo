"""Code-owned deterministic Evidence Bundle assembly."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from app.domains.chat.application.both_retrieval import BothRetrievalResult
from app.domains.chat.application.canonical_retrieval import CanonicalPlanningResult
from app.domains.chat.application.graph_retrieval import GraphPlanningResult
from app.domains.chat.domain.evidence_bundle import (
    MAX_EVIDENCE_BUNDLE_CHARS,
    MAX_EVIDENCE_ITEM_CHARS,
    MAX_EVIDENCE_ITEMS,
    EvidenceBundle,
    EvidenceItem,
    EvidenceKind,
    EvidenceLocator,
    EvidenceLocatorKind,
    compute_evidence_hash,
    opaque_evidence_reference,
)
from app.domains.chat.domain.response_request import (
    DegradedReason,
    RetrievalAxis,
    RetrievalOutcome,
)
from app.domains.chat.domain.retrieval_intent import RetrievalRoute
from app.domains.chat.domain.today_sns_activity import (
    TodaySnsActivityEntry,
    TodaySnsActivitySnapshot,
)
from app.domains.memory.public import (
    CanonicalRecallStatus,
    MemorySourceTypeV1,
    SOURCE_KIND_BY_TYPE,
)
from app.domains.relationships.public import GraphRecallStatus


class EvidenceBundleAssembler:
    """Freeze only revalidated typed retrieval outputs into provider-safe prose."""

    def current_context(
        self,
        *,
        request_id: str,
        request_scope_hash: str,
    ) -> EvidenceBundle:
        return self._bundle(
            request_id=request_id,
            request_scope_hash=request_scope_hash,
            route=RetrievalRoute.CURRENT_CONTEXT,
            outcome=RetrievalOutcome.CURRENT_CONTEXT,
            candidates=(),
        )

    def clarification(
        self,
        *,
        request_id: str,
        request_scope_hash: str,
        slot: str,
    ) -> EvidenceBundle:
        return self._bundle(
            request_id=request_id,
            request_scope_hash=request_scope_hash,
            route=RetrievalRoute.CLARIFICATION,
            outcome=RetrievalOutcome.CLARIFICATION_REQUIRED,
            candidates=(),
            clarification_slot=slot,
        )

    def canonical(
        self,
        *,
        request_scope_hash: str,
        result: CanonicalPlanningResult,
    ) -> EvidenceBundle:
        candidates = self._canonical_items(result)
        if candidates:
            outcome = RetrievalOutcome.MEMORY_USED
            degraded = None
        elif result.metrics.short_circuit_reason == "memory_opt_out":
            outcome = RetrievalOutcome.MEMORY_OFF
            degraded = None
        else:
            outcome = RetrievalOutcome.NO_EVIDENCE
            degraded = DegradedReason.NO_ACCEPTED_EVIDENCE
        return self._bundle(
            request_id=result.request_id,
            request_scope_hash=request_scope_hash,
            route=RetrievalRoute.CANONICAL,
            outcome=outcome,
            candidates=candidates,
            degraded_reason=degraded,
        )

    def graph(
        self,
        *,
        request_scope_hash: str,
        result: GraphPlanningResult,
        character_labels: Mapping[str, str],
    ) -> EvidenceBundle:
        candidates = self._graph_items(result, character_labels)
        degraded_result = self._graph_degraded(result)
        if candidates:
            outcome = (
                RetrievalOutcome.DEGRADED
                if degraded_result
                else RetrievalOutcome.RELATIONSHIP_USED
            )
            degraded = (
                DegradedReason.GRAPH_UNAVAILABLE if degraded_result else None
            )
        else:
            outcome = RetrievalOutcome.NO_EVIDENCE
            degraded = (
                DegradedReason.GRAPH_UNAVAILABLE
                if degraded_result
                else DegradedReason.NO_ACCEPTED_EVIDENCE
            )
        return self._bundle(
            request_id=result.request_id,
            request_scope_hash=request_scope_hash,
            route=RetrievalRoute.GRAPH,
            outcome=outcome,
            candidates=candidates,
            degraded_reason=degraded,
        )

    def both(
        self,
        *,
        request_scope_hash: str,
        result: BothRetrievalResult,
        character_labels: Mapping[str, str],
    ) -> EvidenceBundle:
        canonical = (
            () if result.canonical is None else self._canonical_items(result.canonical)
        )
        graph = () if result.graph is None else self._graph_items(
            result.graph,
            character_labels,
        )
        partial: list[RetrievalAxis] = []
        if not canonical:
            partial.append(RetrievalAxis.CANONICAL)
        if not graph:
            partial.append(RetrievalAxis.GRAPH)
        if canonical and graph:
            outcome = RetrievalOutcome.BOTH_USED
            degraded = None
            partial = []
        elif canonical or graph:
            outcome = RetrievalOutcome.DEGRADED
            degraded = (
                DegradedReason.CANONICAL_UNAVAILABLE
                if not canonical
                else DegradedReason.GRAPH_UNAVAILABLE
            )
        else:
            outcome = RetrievalOutcome.NO_EVIDENCE
            degraded = DegradedReason.NO_ACCEPTED_EVIDENCE
        return self._bundle(
            request_id=result.request_id,
            request_scope_hash=request_scope_hash,
            route=RetrievalRoute.BOTH,
            outcome=outcome,
            candidates=canonical + graph,
            partial_axes=tuple(partial),
            degraded_reason=degraded,
        )

    def with_today_sns(
        self,
        bundle: EvidenceBundle,
        snapshot: TodaySnsActivitySnapshot | None,
        *,
        user_message: str,
    ) -> EvidenceBundle:
        """Merge the immutable same-generation Today snapshot into evidence.

        The snapshot contains canonical identifiers for revalidation and the
        private inspector. Provider payloads continue to expose only bounded
        prose plus opaque references.
        """

        if snapshot is None or bundle.route is RetrievalRoute.CLARIFICATION:
            return bundle
        available_slots = max(0, MAX_EVIDENCE_ITEMS - len(bundle.items))
        selected_entries = self._select_today_entries(
            snapshot.entries,
            user_message=user_message,
            limit=available_slots,
            prefer_full_context=bundle.route is RetrievalRoute.CURRENT_CONTEXT,
        )
        today_items = tuple(
            item
            for entry in selected_entries
            if (item := self._today_item(entry)) is not None
        )
        if not today_items:
            return bundle
        outcome = bundle.retrieval_outcome
        degraded_reason = bundle.degraded_reason
        if outcome is RetrievalOutcome.NO_EVIDENCE:
            outcome = RetrievalOutcome.DEGRADED
            degraded_reason = (
                DegradedReason.GRAPH_UNAVAILABLE
                if bundle.route is RetrievalRoute.GRAPH
                else DegradedReason.CANONICAL_UNAVAILABLE
            )
        return self._bundle(
            request_id=bundle.request_id,
            request_scope_hash=bundle.request_scope_hash,
            route=bundle.route,
            outcome=outcome,
            candidates=bundle.items + today_items,
            partial_axes=bundle.partial_axes,
            degraded_reason=degraded_reason,
            clarification_slot=bundle.clarification_slot,
        )

    @staticmethod
    def _select_today_entries(
        entries: tuple[TodaySnsActivityEntry, ...],
        *,
        user_message: str,
        limit: int,
        prefer_full_context: bool,
    ) -> tuple[TodaySnsActivityEntry, ...]:
        if limit <= 0 or not entries:
            return ()
        message = " ".join(user_message.casefold().split())
        kinds: set[str] = set()
        if any(marker in message for marker in ("게시글", "지저귐", "포스트")):
            kinds.add("posts_authored")
        if any(marker in message for marker in ("대꾸", "댓글", "답글", "리플")):
            kinds.update(("replies_authored", "replies_received", "mentions_received"))
        if any(marker in message for marker in ("좋아요", "리액션")):
            kinds.update(("reactions_given", "reactions_received"))
        if "리포스트" in message:
            kinds.add("reposts")
        if "팔로우" in message:
            kinds.add("follows")
        asks_subjective = any(
            marker in message for marker in ("왜", "이유", "동기", "기분", "감정")
        )

        def score(entry: TodaySnsActivityEntry) -> tuple[int, float, str]:
            value = 0
            if not kinds or entry.kind in kinds:
                value += 8
            for label, weight in (
                (entry.counterpart_label, 7),
                (entry.actor_label, 3),
            ):
                if label and label.casefold() in message:
                    value += weight
            if asks_subjective and entry.subjective_context is not None:
                value += 6
            if any(marker in message for marker in ("방금", "최근", "아까")):
                value += 1
            return (
                value,
                entry.occurred_at.astimezone(UTC).timestamp(),
                entry.opaque_reference,
            )

        ranked = sorted(entries, key=score, reverse=True)
        if kinds:
            matched = [entry for entry in ranked if entry.kind in kinds]
            if matched:
                ranked = matched
        contextual_limit = limit if prefer_full_context or kinds else min(limit, 4)
        return tuple(ranked[:contextual_limit])

    @staticmethod
    def _canonical_items(
        result: CanonicalPlanningResult,
    ) -> tuple[EvidenceItem, ...]:
        if result.execution is None:
            return ()
        items: list[EvidenceItem] = []
        for step in result.execution.steps:
            if step.result.status is not CanonicalRecallStatus.READY:
                continue
            for record in step.result.records:
                text = EvidenceBundleAssembler._bounded_text(record.text)
                if not text:
                    continue
                items.append(
                    EvidenceItem(
                        opaque_reference=opaque_evidence_reference(
                            "canonical",
                            record.canonical_source_id,
                            record.reference,
                        ),
                        kind=EvidenceKind.CANONICAL_SOURCE,
                        text=text,
                        occurred_at=EvidenceBundleAssembler._aware(record.occurred_at),
                        axes=(RetrievalAxis.CANONICAL,),
                        locator=_record_locator(record),
                    )
                )
        return tuple(items)

    @staticmethod
    def _graph_items(
        result: GraphPlanningResult,
        labels: Mapping[str, str],
    ) -> tuple[EvidenceItem, ...]:
        if result.execution is None:
            return ()
        items: list[EvidenceItem] = []
        for graph_result in result.execution.results:
            if graph_result.status not in {
                GraphRecallStatus.READY,
                GraphRecallStatus.LAGGING,
            }:
                continue
            for relationship in graph_result.relationships:
                actor = labels.get(
                    relationship.actor_world_character_id,
                    "말하는 Character",
                )
                target = labels.get(
                    relationship.target_world_character_id,
                    "상대 Character",
                )
                text = (
                    f"{actor}에서 {target} 방향의 현재 관계: "
                    f"친숙도 {relationship.familiarity}, 호감 {relationship.affinity}, "
                    f"신뢰 {relationship.trust}, 긴장 {relationship.tension}, "
                    f"상호작용 {relationship.interaction_count}회."
                )
                items.append(
                    EvidenceItem(
                        opaque_reference=opaque_evidence_reference(
                            "graph-relationship",
                            relationship.relationship_state_id,
                            str(relationship.relationship_version),
                        ),
                        kind=EvidenceKind.GRAPH_RELATIONSHIP,
                        text=text,
                        occurred_at=EvidenceBundleAssembler._aware(
                            relationship.updated_at or relationship.last_event_at
                        ),
                        axes=(RetrievalAxis.GRAPH,),
                        locator=EvidenceLocator(
                            kind=EvidenceLocatorKind.GRAPH_RELATIONSHIP,
                            source_id=relationship.relationship_state_id,
                            source_revision=str(relationship.relationship_version),
                            actor_world_character_id=(
                                relationship.actor_world_character_id
                            ),
                            target_world_character_id=(
                                relationship.target_world_character_id
                            ),
                        ),
                    )
                )
            for event in graph_result.evidence:
                actor = labels.get(event.actor_world_character_id, "한 Character")
                target = (
                    None
                    if event.target_world_character_id is None
                    else labels.get(event.target_world_character_id, "상대 Character")
                )
                target_text = "" if target is None else f" → {target}"
                items.append(
                    EvidenceItem(
                        opaque_reference=opaque_evidence_reference(
                            "graph-event",
                            event.event_id,
                        ),
                        kind=EvidenceKind.GRAPH_EVENT,
                        text=f"{actor}{target_text} 사이에 성공한 {event.event_type} 사건이 있었음.",
                        occurred_at=EvidenceBundleAssembler._aware(event.occurred_at),
                        axes=(RetrievalAxis.GRAPH,),
                        locator=EvidenceLocator(
                            kind=EvidenceLocatorKind.CANONICAL_SOURCE,
                            source_type=MemorySourceTypeV1.SOCIAL_EVENT.value,
                            source_id=event.event_id,
                            actor_world_character_id=(
                                event.actor_world_character_id
                            ),
                            target_world_character_id=(
                                event.target_world_character_id
                            ),
                        ),
                    )
                )
        return tuple(items)

    @staticmethod
    def _graph_degraded(result: GraphPlanningResult) -> bool:
        return bool(
            result.execution
            and any(
                item.status is GraphRecallStatus.DEGRADED
                for item in result.execution.results
            )
        )

    def _bundle(
        self,
        *,
        request_id: str,
        request_scope_hash: str,
        route: RetrievalRoute,
        outcome: RetrievalOutcome,
        candidates: tuple[EvidenceItem, ...],
        partial_axes: tuple[RetrievalAxis, ...] = (),
        degraded_reason: DegradedReason | None = None,
        clarification_slot: str | None = None,
    ) -> EvidenceBundle:
        items = self._dedupe_sort_truncate(candidates)
        evidence_hash = compute_evidence_hash(
            request_id=request_id,
            request_scope_hash=request_scope_hash,
            route=route,
            retrieval_outcome=outcome,
            items=items,
            partial_axes=partial_axes,
            degraded_reason=degraded_reason,
            clarification_slot=clarification_slot,
        )
        return EvidenceBundle(
            request_id=request_id,
            request_scope_hash=request_scope_hash,
            route=route,
            retrieval_outcome=outcome,
            items=items,
            partial_axes=partial_axes,
            degraded_reason=degraded_reason,
            clarification_slot=clarification_slot,
            evidence_hash=evidence_hash,
        )

    @staticmethod
    def _dedupe_sort_truncate(
        candidates: tuple[EvidenceItem, ...],
    ) -> tuple[EvidenceItem, ...]:
        deduplicated: dict[tuple[str, str], EvidenceItem] = {}
        for item in candidates:
            key = (item.kind.value, item.normalized_text.casefold())
            existing = deduplicated.get(key)
            if existing is None:
                deduplicated[key] = item
                continue
            axes = tuple(
                axis
                for axis in (RetrievalAxis.CANONICAL, RetrievalAxis.GRAPH)
                if axis in set(existing.axes) | set(item.axes)
            )
            occurred_at = max(
                (value for value in (existing.occurred_at, item.occurred_at) if value),
                default=None,
            )
            deduplicated[key] = EvidenceItem(
                opaque_reference=min(existing.opaque_reference, item.opaque_reference),
                kind=existing.kind,
                text=existing.text,
                occurred_at=occurred_at,
                axes=axes,
                locator=existing.locator or item.locator,
            )
        ordered = sorted(
            deduplicated.values(),
            key=lambda item: (
                -(
                    item.occurred_at.astimezone(UTC).timestamp()
                    if item.occurred_at is not None
                    else 0
                ),
                item.kind.value,
                item.opaque_reference,
            ),
        )
        output: list[EvidenceItem] = []
        chars = 0
        for item in ordered:
            if len(output) >= MAX_EVIDENCE_ITEMS:
                break
            if chars + len(item.text) > MAX_EVIDENCE_BUNDLE_CHARS:
                continue
            output.append(item)
            chars += len(item.text)
        return tuple(output)

    @staticmethod
    def _today_item(entry: TodaySnsActivityEntry) -> EvidenceItem | None:
        parts = [
            f"오늘 SNS 활동 종류: {entry.kind}",
            f"실제 행동: {entry.event_type}",
            f"행동 주체: {entry.actor_label}",
        ]
        if entry.counterpart_label is not None:
            parts.append(f"상대: {entry.counterpart_label}")
        if entry.truncated:
            parts.append("원문 일부만 포함됨: 전문이나 전체 대화로 주장하지 말 것")
        if entry.root_title:
            parts.append(f"대화 시작 글 제목: {entry.root_title}")
        if entry.root_body:
            parts.append(f"대화 시작 글 일부: {entry.root_body}")
        if entry.parent_title:
            parts.append(f"직접 연결된 이전 글 제목: {entry.parent_title}")
        if entry.parent_body:
            parts.append(f"직접 연결된 이전 글: {entry.parent_body}")
        if entry.title:
            parts.append(f"제목: {entry.title}")
        if entry.body:
            parts.append(f"내용: {entry.body}")
        subjective = entry.subjective_context
        if subjective is not None:
            parts.append(
                "행동 결정 시 직접 선언한 동기: "
                f"{subjective.motivation_text} ({subjective.motivation_kind})"
            )
            if subjective.emotion_label != "unspecified":
                emotion = subjective.emotion_label
                if subjective.emotion_text:
                    emotion = f"{emotion}: {subjective.emotion_text}"
                if subjective.emotion_intensity is not None:
                    emotion = f"{emotion} (강도 {subjective.emotion_intensity}/100)"
                parts.append(f"행동 결정 시 직접 선언한 감정: {emotion}")
        text = EvidenceBundleAssembler._bounded_text(" | ".join(parts))
        if not text:
            return None
        source_type = (
            MemorySourceTypeV1.SOCIAL_EVENT
            if entry.source_type == "social_event"
            else MemorySourceTypeV1.REPLY
            if entry.source_post_id is not None
            and entry.kind
            in {"replies_authored", "replies_received", "mentions_received"}
            else MemorySourceTypeV1.POST
            if entry.source_post_id is not None
            else MemorySourceTypeV1.SOCIAL_EVENT
        )
        source_id = entry.source_id
        return EvidenceItem(
            opaque_reference=entry.opaque_reference,
            kind=EvidenceKind.TODAY_SNS_ACTIVITY,
            text=text,
            occurred_at=EvidenceBundleAssembler._aware(entry.occurred_at),
            axes=(RetrievalAxis.CANONICAL,),
            locator=EvidenceLocator(
                kind=EvidenceLocatorKind.CANONICAL_SOURCE,
                source_type=source_type.value,
                source_id=source_id,
                source_revision=entry.source_revision,
            ),
        )

    @staticmethod
    def _bounded_text(value: str) -> str:
        return " ".join(value.split())[:MAX_EVIDENCE_ITEM_CHARS].strip()

    @staticmethod
    def _aware(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return (
            value.replace(tzinfo=UTC)
            if value.tzinfo is None
            else value.astimezone(UTC)
        )


__all__ = ["EvidenceBundleAssembler"]


def _record_source_type(record) -> MemorySourceTypeV1 | None:
    if record.source_type is not None:
        return record.source_type
    return next(
        (
            source_type
            for source_type, kind in SOURCE_KIND_BY_TYPE.items()
            if kind is record.kind
        ),
        None,
    )


def _record_locator(record) -> EvidenceLocator | None:
    source_type = _record_source_type(record)
    if source_type is not None:
        return EvidenceLocator(
            kind=EvidenceLocatorKind.CANONICAL_SOURCE,
            source_id=record.canonical_source_id,
            source_type=source_type.value,
            source_revision=record.metadata.get("source_digest"),
        )

    if record.memory_item_id is not None:
        return EvidenceLocator(
            kind=EvidenceLocatorKind.MEMORY_ITEM,
            source_id=record.memory_item_id,
            source_revision=record.metadata.get("item_version"),
        )
    return None
