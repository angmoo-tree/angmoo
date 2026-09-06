"""Bounded Today SNS visibility, causal source validation and snapshot assembly."""

from __future__ import annotations
from collections import Counter
from datetime import datetime
from sqlalchemy.orm import Session
from app.domains.social.contracts.subjective_context import (
    ActionEmotionLabel,
    ActionMotivationKind,
    ActionSubjectiveContextV1,
    SubjectiveContextProvenance,
)
from app.domains.social.contracts.today_activity import (
    TodaySocialActivityKind,
    TodaySocialActivityRead,
    TodaySocialActivityRecord,
    TodaySocialCoverageStatus,
    TodaySocialSubjectiveRecord,
)
from app.domains.social.contracts.today_references import TodayReferences
from app.domains.social.repository.today_activity import TodayActivityRepository
from app.domains.social.service.subjective_context import subjective_context_digest
from app.domains.social.constants import (
    MAX_TODAY_SOCIAL_RECORDS,
    MAX_TODAY_BRANCH_DEPTH,
    MAX_TODAY_QUERY_BATCH,
    _VISIBLE_POST_VISIBILITIES,
    _POST_EVENT_TYPES,
)
from app.domains.social.exceptions import TodaySocialActivityReadError
from app.domains.social.service.today_activity_values import (
    _execution_matches,
    _event_kind,
    _chain_revision,
    _source_revision,
    _watermark,
    _aware,
)


class TodaySocialActivityService:
    def __init__(self, db: Session, *, references: TodayReferences) -> None:
        self.repository = TodayActivityRepository(db)
        self.references = references

    def read(
        self,
        *,
        owner_id: str,
        world_id: str,
        subject_world_character_id: str,
        started_at: datetime,
        complete_through: datetime,
    ) -> TodaySocialActivityRead:
        start, end = (_aware(started_at), _aware(complete_through))
        if end < start:
            raise TodaySocialActivityReadError("today_social_day_range_invalid")
        self._validate_scope(owner_id, world_id, subject_world_character_id)
        active = self.references._active_world_character_ids(world_id)
        blocked = self.repository._blocked_counterparts(
            world_id, subject_world_character_id
        )
        events, event_overflow = self.references.events(
            world_id, subject_world_character_id, start, end
        )
        own_posts, own_overflow = self.repository.authored(
            world_id, subject_world_character_id, start, end
        )
        received, received_overflow = self.repository.received(
            world_id, subject_world_character_id, start, end
        )
        evidence_rows = self.references.evidence([event.id for event in events])
        evidence_by_event = {}
        for evidence in sorted(evidence_rows, key=lambda row: row.id):
            evidence_by_event.setdefault(evidence.social_event_id, evidence)
        executions = {
            row.id: row
            for row in self.references.executions(
                [
                    row.public_action_execution_id
                    for row in evidence_rows
                    if row.public_action_execution_id is not None
                ]
            )
        }
        post_ids = {post.id for post in own_posts + received}
        for evidence in evidence_rows:
            post_ids.update(
                (
                    value
                    for value in (
                        evidence.source_post_id,
                        evidence.target_post_id,
                        evidence.root_post_id,
                    )
                    if value is not None
                )
            )
        posts = {post.id: post for post in own_posts + received}
        posts.update({row.id: row for row in self.repository.posts(post_ids)})
        frontier = {
            post.reply_to_post_id
            for post in posts.values()
            if post.reply_to_post_id is not None and post.reply_to_post_id not in posts
        }
        for _ in range(MAX_TODAY_BRANCH_DEPTH):
            if not frontier:
                break
            ancestors = self.repository.posts(frontier)
            posts.update({post.id: post for post in ancestors})
            frontier = {
                post.reply_to_post_id
                for post in ancestors
                if post.reply_to_post_id is not None
                and post.reply_to_post_id not in posts
            }

        def visible(post_id):
            post = posts.get(post_id)
            if (
                post is None
                or post.world_id != world_id
                or post.deleted_at is not None
                or (post.report_hidden_at is not None)
                or (post.visibility not in _VISIBLE_POST_VISIBILITIES)
                or (post.author_world_character_id not in active)
                or (post.author_world_character_id in blocked)
            ):
                return None
            return post

        ancestry_unknown = False

        def lineage(post):
            nonlocal ancestry_unknown
            if post is None:
                return None
            chain, seen = ([], set())
            current = post
            for _ in range(MAX_TODAY_BRANCH_DEPTH + 1):
                if current.id in seen:
                    ancestry_unknown = True
                    return None
                if visible(current.id) is None:
                    return None
                seen.add(current.id)
                chain.append(current)
                if current.reply_to_post_id is None:
                    return chain
                parent_id = current.reply_to_post_id
                current = visible(parent_id)
                if current is None:
                    if parent_id not in posts:
                        ancestry_unknown = True
                    return None
            ancestry_unknown = True
            return None

        subjective = self._subjective_by_event(
            owner_id,
            world_id,
            subject_world_character_id,
            events,
            evidence_by_event,
            executions,
        )
        records = {}
        post_event_ids = {
            event.id for event in events if event.event_type in _POST_EVENT_TYPES
        }
        represented_posts = {
            row.source_post_id
            for row in evidence_rows
            if row.source_post_id is not None and row.social_event_id in post_event_ids
        }
        candidate_post_ids = sorted({post.id for post in own_posts + received})
        for offset in range(0, len(candidate_post_ids), MAX_TODAY_QUERY_BATCH):
            represented_posts.update(
                self.references.represented_post_ids(
                    world_id,
                    candidate_post_ids[offset : offset + MAX_TODAY_QUERY_BATCH],
                )
            )
        for event in events:
            counterpart = (
                event.target_world_character_id
                if event.actor_world_character_id == subject_world_character_id
                else event.actor_world_character_id
            )
            evidence = evidence_by_event.get(event.id)
            execution = (
                None
                if evidence is None
                else executions.get(evidence.public_action_execution_id)
            )
            if (
                event.actor_world_character_id not in active
                or (counterpart is not None and counterpart not in active)
                or counterpart in blocked
                or (event.result != "succeeded")
                or (event.retrieval_status not in {"eligible", "audit_only"})
                or (event.invalidated_at is not None)
                or (evidence is None)
                or (
                    evidence.public_action_execution_id is not None
                    and (not _execution_matches(execution, event))
                )
            ):
                continue
            post_id = evidence.source_post_id or evidence.target_post_id
            post = visible(post_id)
            chain = lineage(post) if post_id is not None else []
            if post_id is not None and chain is None:
                continue
            if event.event_type in _POST_EVENT_TYPES and (
                post is None
                or post.author_world_character_id != event.actor_world_character_id
            ):
                continue
            if evidence.root_post_id is not None and (
                not chain or chain[-1].id != evidence.root_post_id
            ):
                continue
            if (
                evidence.target_post_id is not None
                and visible(evidence.target_post_id) is None
            ):
                continue
            kind = _event_kind(event, subject_world_character_id)
            if kind is None:
                continue
            parent = chain[1] if chain and len(chain) > 1 else None
            if kind is TodaySocialActivityKind.REPLY_RECEIVED and (
                parent is None
                or parent.author_world_character_id != subject_world_character_id
            ):
                continue
            key = f"event:{event.id}"
            records[key] = TodaySocialActivityRecord(
                record_key=key,
                kind=kind,
                source_type="social_event",
                source_id=event.id,
                source_revision=_source_revision(
                    event, evidence, chain or [], subjective.get(event.id)
                ),
                actor_world_character_id=event.actor_world_character_id,
                counterpart_world_character_id=counterpart,
                event_type=event.event_type,
                occurred_at=_aware(event.occurred_at),
                root_post_id=None if not chain else chain[-1].id,
                source_post_id=None if post is None else post.id,
                target_post_id=evidence.target_post_id,
                title=None if post is None else post.title,
                body=None if post is None else post.body,
                parent_title=None if parent is None else parent.title,
                parent_body=None if parent is None else parent.body,
                root_title=chain[-1].title if chain and len(chain) > 2 else None,
                root_body=chain[-1].body if chain and len(chain) > 2 else None,
                subjective_context=subjective.get(event.id),
            )
        for post in own_posts + received:
            if post.id in represented_posts:
                continue
            chain = lineage(post)
            if chain is None:
                continue
            parent = chain[1] if len(chain) > 1 else None
            outgoing = post.author_world_character_id == subject_world_character_id
            if not outgoing and (
                parent is None
                or parent.author_world_character_id != subject_world_character_id
            ):
                continue
            kind = (
                TodaySocialActivityKind.REPLY_AUTHORED
                if outgoing and parent is not None
                else TodaySocialActivityKind.POST_AUTHORED
                if outgoing
                else TodaySocialActivityKind.REPLY_RECEIVED
            )
            counterpart = (
                (None if parent is None else parent.author_world_character_id)
                if outgoing
                else subject_world_character_id
            )
            key = f"post:{post.id}"
            records[key] = TodaySocialActivityRecord(
                record_key=key,
                kind=kind,
                source_type="post",
                source_id=post.id,
                source_revision=_chain_revision(chain),
                actor_world_character_id=post.author_world_character_id,
                counterpart_world_character_id=counterpart,
                event_type="post_published" if parent is None else "reply_created",
                occurred_at=_aware(post.created_at),
                root_post_id=chain[-1].id,
                source_post_id=post.id,
                target_post_id=post.reply_to_post_id,
                title=post.title,
                body=post.body,
                parent_title=None if parent is None else parent.title,
                parent_body=None if parent is None else parent.body,
                root_title=chain[-1].title if len(chain) > 2 else None,
                root_body=chain[-1].body if len(chain) > 2 else None,
            )
        ordered = sorted(
            records.values(),
            key=lambda row: (row.occurred_at, row.record_key),
            reverse=True,
        )
        counts = Counter((record.kind.value for record in ordered))
        complete_counts = {
            kind.value: int(counts[kind.value]) for kind in TodaySocialActivityKind
        }
        scan_overflow = (
            event_overflow or own_overflow or received_overflow or ancestry_unknown
        )
        selected = tuple(ordered[:MAX_TODAY_SOCIAL_RECORDS])
        selected_counts = Counter((record.kind.value for record in selected))
        return TodaySocialActivityRead(
            records=selected,
            counts=complete_counts,
            coverage={
                kind.value: TodaySocialCoverageStatus.PARTIAL
                if scan_overflow or selected_counts[kind.value] < counts[kind.value]
                else TodaySocialCoverageStatus.COMPLETE
                for kind in TodaySocialActivityKind
            },
            source_watermarks={
                "social": _watermark(events),
                "canonical_post": _watermark(list(posts.values())),
                "subjective_context": _watermark(
                    list(subjective.values()), attribute="source_digest"
                ),
            },
            overflow=scan_overflow or len(ordered) > MAX_TODAY_SOCIAL_RECORDS,
            counts_exact=not scan_overflow,
        )

    def _validate_scope(self, owner_id, world_id, subject_id) -> None:
        world, subject, membership = self.references.scope(world_id, subject_id)
        if (
            world is None
            or world.owner_user_id != owner_id
            or subject is None
            or (subject.world_id != world_id)
            or (subject.status != "active")
            or (membership is None)
            or (membership.world_id != world_id)
            or (membership.status != "active")
        ):
            raise TodaySocialActivityReadError("today_social_scope_forbidden")

    def _subjective_by_event(
        self, owner_id, world_id, subject_id, events, evidence_by_event, executions
    ):
        rows = self.repository.subjective([event.id for event in events])
        event_by_id, output = ({event.id: event for event in events}, {})
        for row in rows:
            event, evidence = (
                event_by_id.get(row.social_event_id),
                evidence_by_event.get(row.social_event_id),
            )
            execution = executions.get(row.public_action_execution_id)
            if (
                row.owner_id != owner_id
                or row.world_id != world_id
                or row.actor_world_character_id != subject_id
                or (row.invalidated_at is not None)
                or (event is None)
                or (evidence is None)
                or (event.actor_world_character_id != subject_id)
                or (event.result != "succeeded")
                or (event.invalidated_at is not None)
                or (
                    evidence.public_action_execution_id
                    != row.public_action_execution_id
                )
                or (not _execution_matches(execution, event))
                or (_aware(row.captured_at) > _aware(event.occurred_at))
            ):
                continue
            try:
                context = ActionSubjectiveContextV1(
                    version=row.schema_version,
                    motivation_kind=ActionMotivationKind(row.motivation_kind),
                    motivation_text=row.motivation_text,
                    emotion_label=ActionEmotionLabel(row.emotion_label),
                    emotion_text=row.emotion_text,
                    emotion_intensity=row.emotion_intensity,
                    provenance_kind=SubjectiveContextProvenance(row.provenance_kind),
                )
                digest = subjective_context_digest(
                    execution=execution,
                    event=event,
                    source_content_digest=evidence.content_sha256,
                    context=context,
                )
            except (TypeError, ValueError):
                continue
            if row.source_digest != digest:
                continue
            output[row.social_event_id] = TodaySocialSubjectiveRecord(
                motivation_kind=context.motivation_kind.value,
                motivation_text=context.normalized_motivation_text,
                emotion_label=context.emotion_label.value,
                emotion_text=context.normalized_emotion_text,
                emotion_intensity=context.emotion_intensity,
                source_digest=digest,
            )
        return output
