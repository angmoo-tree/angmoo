"""Manual reply eligibility and fenced inbox lifecycle with original commit semantics."""

from datetime import datetime
from sqlalchemy.orm import Session
from app.domains.social.contracts.inbox import (
    ManualInboxInteractionCandidate,
    ManualInboxReferences,
    ManualInboxRuntimeError,
)
from app.domains.social.models.manual_writes import OwnerManualInboxCandidate
from app.domains.social.models.posts import Post
from app.domains.social.repository import manual_inbox as repository, posts
from app.domains.social.utils.manual_inbox import source_id, candidate_id, _aware_utc


class ManualInboxService:
    def __init__(self, references: ManualInboxReferences) -> None:
        self.references = references

    def _valid_candidate(
        self, db: Session, *, row: OwnerManualInboxCandidate
    ) -> tuple[Post, Post] | None:
        reply = posts.get_post(db, row.source_reply_post_id)
        target_post = posts.get_post(db, row.target_post_id)
        actor = self.references.get_world_character(db, row.actor_world_character_id)
        target = self.references.get_world_character(db, row.target_world_character_id)
        if (
            reply is None
            or target_post is None
            or actor is None
            or (target is None)
            or (reply.world_id != row.world_id)
            or (target_post.world_id != row.world_id)
            or (reply.author_world_character_id != actor.id)
            or (target_post.author_world_character_id != target.id)
            or (reply.reply_to_post_id != target_post.id)
            or (reply.deleted_at is not None)
            or (target_post.deleted_at is not None)
            or (reply.report_hidden_at is not None)
            or (target_post.report_hidden_at is not None)
            or (reply.visibility != "public")
            or (target_post.visibility != "public")
            or (actor.status != "active")
            or (actor.control_mode != "owner_controlled")
            or (target.status != "active")
            or (target.control_mode != "autonomous")
            or (target.activity_runtime_mode != "routine_resident_v1")
            or repository._blocked(db, row=row)
        ):
            return None
        actor_membership = self.references.get_membership(db, actor.membership_id)
        target_membership = self.references.get_membership(db, target.membership_id)
        if (
            actor_membership is None
            or target_membership is None
            or actor_membership.world_id != row.world_id
            or (target_membership.world_id != row.world_id)
            or (actor_membership.status != "active")
            or (target_membership.status != "active")
        ):
            return None
        return (reply, target_post)

    def candidates(
        self,
        db: Session,
        *,
        world_id: str,
        consumer_world_character_id: str,
        episode_id: str,
        after: datetime,
        before: datetime,
    ) -> list[ManualInboxInteractionCandidate]:
        current = _aware_utc(before)
        rows = repository.list_candidates(
            db,
            world_id=world_id,
            consumer_world_character_id=consumer_world_character_id,
            after=after,
            before=before,
            current=current,
        )
        result: list[ManualInboxInteractionCandidate] = []
        rejected = False
        for row in rows:
            valid = self._valid_candidate(db, row=row)
            if valid is None:
                row.status = "rejected"
                row.rejected_reason_code = "source_context_invalid"
                row.claim_run_id = None
                row.claim_expires_at = None
                row.target_activity_beat_id = None
                row.version += 1
                rejected = True
                continue
            reply, target_post = valid
            result.append(
                ManualInboxInteractionCandidate(
                    source_event_id=source_id(row.id),
                    world_id=row.world_id,
                    consumer_world_character_id=row.target_world_character_id,
                    actor_world_character_id=row.actor_world_character_id,
                    excerpt=reply.body,
                    occurred_at=row.created_at,
                    directness=100,
                    episode_relevance=100
                    if target_post.activity_episode_id == episode_id
                    else 60,
                    relationship_band="new",
                )
            )
        if rejected:
            db.commit()
        return result

    def claim(
        self,
        db: Session,
        *,
        source_event_id: str,
        world_id: str,
        consumer_world_character_id: str,
        target_activity_beat_id: str,
        claim_run_id: str,
        claim_expires_at: datetime,
        now: datetime,
    ) -> OwnerManualInboxCandidate:
        row_id = candidate_id(source_event_id)
        if row_id is None:
            raise ManualInboxRuntimeError("manual_inbox_source_invalid")
        current = _aware_utc(now)
        expiry = _aware_utc(claim_expires_at)
        row = repository.get_for_update(db, row_id)
        if row is None:
            raise ManualInboxRuntimeError("manual_inbox_missing")
        if (
            row.world_id != world_id
            or row.target_world_character_id != consumer_world_character_id
            or self._valid_candidate(db, row=row) is None
        ):
            raise ManualInboxRuntimeError("manual_inbox_scope_invalid")
        if row.status == "consumed":
            raise ManualInboxRuntimeError("manual_inbox_already_consumed")
        if row.status == "rejected":
            raise ManualInboxRuntimeError("manual_inbox_rejected")
        if (
            row.status == "claimed"
            and row.claim_run_id != claim_run_id
            and (row.claim_expires_at is not None)
            and (_aware_utc(row.claim_expires_at) > current)
        ):
            raise ManualInboxRuntimeError("manual_inbox_already_claimed")
        row.status = "claimed"
        row.target_activity_beat_id = target_activity_beat_id
        row.claim_run_id = claim_run_id
        row.claim_expires_at = expiry
        row.rejected_reason_code = None
        row.version += 1
        db.commit()
        return row

    def claimed_observation_post_id(
        self,
        db: Session,
        *,
        source_event_id: str,
        world_id: str,
        consumer_world_character_id: str,
        target_activity_beat_id: str,
        claim_run_id: str,
    ) -> str:
        """Resolve the canonical reply post behind one fenced manual claim."""
        row_id = candidate_id(source_event_id)
        if row_id is None:
            raise ManualInboxRuntimeError("manual_inbox_source_invalid")
        row = repository.get_candidate(db, row_id)
        if (
            row is None
            or row.world_id != world_id
            or row.target_world_character_id != consumer_world_character_id
            or (row.target_activity_beat_id != target_activity_beat_id)
            or (row.claim_run_id != claim_run_id)
            or (row.status != "claimed")
        ):
            raise ManualInboxRuntimeError("manual_inbox_claim_mismatch")
        valid = self._valid_candidate(db, row=row)
        if valid is None:
            raise ManualInboxRuntimeError("manual_inbox_source_context_invalid")
        reply, _target_post = valid
        return reply.id

    def release_claims(
        self, db: Session, *, source_event_ids: list[str], claim_run_id: str
    ) -> None:
        ids = [
            value
            for value in (candidate_id(item) for item in source_event_ids)
            if value
        ]
        if not ids:
            return
        for row in repository.claimed_for_run(db, ids=ids, claim_run_id=claim_run_id):
            row.status = "released"
            row.target_activity_beat_id = None
            row.claim_run_id = None
            row.claim_expires_at = None
            row.version += 1
        db.commit()

    def consume_claims(
        self,
        db: Session,
        *,
        source_event_ids: list[str],
        target_activity_beat_id: str,
        claim_run_id: str,
        now: datetime,
    ) -> None:
        ids = [
            value
            for value in (candidate_id(item) for item in source_event_ids)
            if value
        ]
        if not ids:
            return
        rows = repository.list_for_update(db, ids)
        if len(rows) != len(ids) or any(
            (
                row.status != "claimed"
                or row.claim_run_id != claim_run_id
                or row.target_activity_beat_id != target_activity_beat_id
                for row in rows
            )
        ):
            raise ManualInboxRuntimeError("manual_inbox_claim_mismatch")
        current = _aware_utc(now)
        for row in rows:
            row.status = "consumed"
            row.claim_run_id = None
            row.claim_expires_at = None
            row.consumed_at = current
            row.version += 1
        db.flush()
