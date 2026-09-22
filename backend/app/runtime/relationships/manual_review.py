"""Compose manual memory receipts and relationship follow-up in one transaction.

Reads are pure. Admission never calls AI; the existing idle worker owns execution.
"""
from collections import defaultdict
from sqlalchemy import select, tuple_
from app.domains.memory.exceptions import MemoryValidationError
from app.domains.memory.models.consolidation_request import MemoryConsolidationRequest
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.memory.models.batch import MemoryBatchSetting
from app.domains.relationships.models.manual_review import RelationshipReviewRequest
from app.domains.relationships.models.personalization import RelationshipReviewWork, RelationshipReviewMemoryReceipt
from app.domains.relationships.service.personalized_metrics import interpreted_policy
from app.domains.world_characters.models import WorldCharacter

TERMINAL = ("completed", "no_relationship_work", "not_applicable")


class ManualRelationshipFollowup:
    def __init__(self, db):
        self.db = db

    def capability(self, scope):
        actor = self.db.get(WorldCharacter, scope.subject_world_character_id)
        applicable = actor is not None and actor.control_mode == "autonomous"
        return {"relationships": applicable, "reason": None if applicable else "owner_controlled_memory_only"}

    def admit(self, scope, row):
        old = self.db.get(RelationshipReviewRequest, row.id)
        if old:
            return
        capable = self.capability(scope)["relationships"]
        if capable and interpreted_policy(self.db, scope.world_id) is None:
            raise MemoryValidationError("relationship_policy_not_ready")
        active = self.db.scalar(select(RelationshipReviewRequest).where(
            RelationshipReviewRequest.scope_setting_id == row.scope_setting_id,
            RelationshipReviewRequest.canonical_request_id.is_(None),
            RelationshipReviewRequest.state.not_in(TERMINAL)).order_by(RelationshipReviewRequest.accepted_at).limit(1))
        if active:
            # A second click must also reuse the memory root, even while only
            # relationship work remains. Admission already holds the scope lock.
            root = self.db.get(MemoryConsolidationRequest, active.memory_request_id)
            row.coalesced_to_request_id = root.coalesced_to_request_id or root.id
            row.state = "queued"
        self.db.add(RelationshipReviewRequest(memory_request_id=row.id, scope_setting_id=row.scope_setting_id,
            canonical_request_id=active.memory_request_id if active else None,
            state="waiting_memory" if capable else "not_applicable", accepted_at=row.accepted_at,
            snapshot=None, work_ids=[]))
        self.db.flush()

    def active(self, setting_id):
        request = self.db.scalar(select(RelationshipReviewRequest).where(
            RelationshipReviewRequest.scope_setting_id == setting_id,
            RelationshipReviewRequest.canonical_request_id.is_(None),
            RelationshipReviewRequest.state.not_in(TERMINAL)).order_by(RelationshipReviewRequest.accepted_at).limit(1))
        return None if request is None else self.db.get(MemoryConsolidationRequest, request.memory_request_id)

    def extend(self, row, value):
        request = self.db.get(RelationshipReviewRequest, row.id)
        if request is None:
            return value
        if request.canonical_request_id:
            request = self.db.get(RelationshipReviewRequest, request.canonical_request_id)
        works = list(self.db.scalars(select(RelationshipReviewWork).where(RelationshipReviewWork.id.in_(request.work_ids))))
        # Work count differs from counterpart count when joining an older root
        # and then reviewing leftovers. Report counterpart progress, not roots.
        completed, changed, kept = set(), set(), set()
        snapshot = request.snapshot or []
        statuses = {}
        for start in range(0, len(snapshot), 100):
            ids = [r["memory_id"] for r in snapshot[start:start+100]]
            if works:
                statuses.update((r.memory_id, r.status) for r in self.db.scalars(select(RelationshipReviewMemoryReceipt).where(
                    RelationshipReviewMemoryReceipt.world_id == works[0].world_id,
                    RelationshipReviewMemoryReceipt.actor_world_character_id == works[0].actor_world_character_id,
                    RelationshipReviewMemoryReceipt.memory_id.in_(ids))))
        grouped = defaultdict(list)
        for ref in snapshot:
            if not ref.get("excluded_reason"):
                grouped[ref["target_id"]].append(ref)
        for target, refs in grouped.items():
            if refs and all(statuses.get(r["memory_id"]) == "applied" for r in refs):
                completed.add(target)
        latest = {}
        for work in works:
            if work.status == "applied" and (work.target_world_character_id not in latest or
                work.id > latest[work.target_world_character_id].id):
                latest[work.target_world_character_id] = work
        for target in completed:
            (changed if (latest[target].result or {}).get("decision") == "update" else kept).add(target)
        failed_works = []
        if works:
            failed_works = list(self.db.scalars(select(RelationshipReviewWork).where(
                RelationshipReviewWork.world_id == works[0].world_id,
                RelationshipReviewWork.actor_world_character_id == works[0].actor_world_character_id,
                tuple_(RelationshipReviewWork.period_key, RelationshipReviewWork.target_world_character_id).in_(
                    [(w.period_key, w.target_world_character_id) for w in works]),
                RelationshipReviewWork.status == "failed")))
        failed = bool(failed_works)
        state = request.state
        if value["state"] not in ("completed", "no_work"):
            flow = "memory_failed" if value["state"] in ("failed", "partial_failed", "paused", "cancelled") else "memory_running"
        elif state == "not_applicable":
            flow = "memory_only_completed"
        elif state == "completed":
            flow = "completed"
        elif state == "no_relationship_work":
            flow = "no_work" if value["state"] == "no_work" else "no_relationship_work"
        elif state == "paused":
            flow = "relationship_paused"
        elif failed:
            flow = "relationship_retry_needed"
        elif works:
            flow = "relationship_running"
        else:
            flow = "relationship_waiting"
        from app.domains.memory.contracts.items import as_utc
        retry_times = [as_utc(w.next_attempt_at) for w in failed_works if w.next_attempt_at]
        projection_pending = False
        if works:
            from app.domains.relationships.models.social import GraphProjectionOutbox, RelationshipState
            projection_pending = self.db.scalar(select(GraphProjectionOutbox.id).join(
                RelationshipState, RelationshipState.id == GraphProjectionOutbox.relationship_state_id).where(
                RelationshipState.world_id == works[0].world_id,
                RelationshipState.actor_world_character_id == works[0].actor_world_character_id,
                RelationshipState.target_world_character_id.in_({w.target_world_character_id for w in works}),
                GraphProjectionOutbox.projection_type == "relationship_snapshot",
                GraphProjectionOutbox.status.in_(("pending", "processing", "dead"))).limit(1)) is not None
        return {**value, "accepted_at": as_utc(value["accepted_at"]), "workflow_version": 1, "followup": "relationships", "flow_state": flow,
            "relationship": {"state": state, "request_id": request.memory_request_id,
                "target_count": None if request.snapshot is None else len({r["target_id"] for r in request.snapshot}),
                "memory_count": None if request.snapshot is None else len(request.snapshot),
                "completed_count": len(completed), "changed_count": len(changed),
                "kept_count": len(kept), "excluded_memory_count": sum(bool(r.get("excluded_reason")) for r in snapshot),
                "projection_pending": projection_pending,
                "retryable": flow in ("memory_failed", "relationship_paused", "relationship_retry_needed"),
                "next_attempt_at": min(retry_times) if retry_times else None,
                "wait_reason": "memory_priority" if flow == "relationship_waiting" else "retry_backoff" if failed else None,
                "last_code": request.last_code or next((w.error_code for w in failed_works + works if w.error_code), None),
                "completed_at": as_utc(request.completed_at) if request.completed_at else None}}

    def retry(self, scope, row):
        request = self.db.get(RelationshipReviewRequest, row.id)
        if request is None:
            raise MemoryValidationError("relationship_request_not_found")
        if request.canonical_request_id:
            request = self.db.get(RelationshipReviewRequest, request.canonical_request_id)
        setting = self.db.get(MemoryScopeSettingModel, request.scope_setting_id)
        config = self.db.get(MemoryBatchSetting, request.scope_setting_id)
        if not setting.enabled or not config.ai_enabled or not config.consent_version:
            raise MemoryValidationError("memory_selection_consent_required")
        if request.state not in TERMINAL:
            request.state, request.last_code = "waiting_memory", None
        # Failed work already retries after next_attempt_at. An explicit click
        # must not bypass a provider's backoff or invalidate successful parts.
