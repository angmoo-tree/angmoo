"""Atomic, idempotent interpretation application, shared by chat and SNS.

Runtime validates real source/delivery ownership through the references port.
This service owns relationship writes; callers own the transaction boundary.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, UTC
from typing import Protocol
from zoneinfo import ZoneInfo
import hashlib
import json

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.ids import uuid7_string
from app.domains.relationships.contracts.metric_interpretation import MetricInterpretation, parse_metric_interpretations
from app.domains.relationships.models.personalization import RelationshipPolicy, RelationshipExperienceReceipt, RelationshipMetricApplication, RelationshipMetricBudget
from app.domains.relationships.models.social import GraphProjectionOutbox, RelationshipState
from app.domains.relationships.policies.personalized_metrics import calculate_metric_delta
from app.domains.relationships.service.state import _relationship_state


@dataclass(frozen=True, slots=True)
class ExperiencedSource:
    world_id: str
    actor_id: str
    target_id: str
    kind: str
    key: str
    revision: str
    occurred_at: datetime
    delivered_at: datetime
    timezone: str


class ExperienceReferences(Protocol):
    def validate(self, source: ExperiencedSource) -> None:
        """Raise unless same owner/World, AI subject, visible source, real delivery."""
        ...


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def interpreted_policy(db: Session, world_id: str) -> RelationshipPolicy | None:
    policy = db.get(RelationshipPolicy, world_id)
    return policy if policy is not None and policy.mode == "interpreted" and policy.activated_at else None


def enqueue_snapshot(db: Session, state: RelationshipState) -> None:
    key = hashlib.sha256(f"relationship_snapshot:{state.id}:{state.version}".encode()).hexdigest()
    if db.scalar(select(GraphProjectionOutbox.id).where(GraphProjectionOutbox.dedupe_key == key)):
        return
    payload = {"world_id": state.world_id, "relationship_state_id": state.id, "relationship_version": state.version}
    db.add(GraphProjectionOutbox(id=uuid7_string(), world_id=state.world_id,
        source_event_id=None, relationship_state_id=state.id, projection_type="relationship_snapshot",
        payload_version="relationship-snapshot-v1", payload=payload,
        source_signature=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
        dedupe_key=key, status="pending", attempt_count=0))


def stage_experience(
    db: Session, *, references: ExperienceReferences, source: ExperiencedSource,
    decision_key: str, interpretation: MetricInterpretation | None, metadata_status: str = "valid",
) -> RelationshipMetricApplication | None:
    """Stage only a confirmed read/turn; candidate queries must never call this.

    Source key excludes retry/request IDs so regeneration cannot earn points.
    Commit alongside the normal completed turn or planner delivery receipt.
    """
    policy = interpreted_policy(db, source.world_id)
    if policy is None or _utc(source.occurred_at) < _utc(policy.activated_at):
        return None
    references.validate(source)
    if source.actor_id == source.target_id or not source.key or len(source.key) > 128:
        raise ValueError("relationship_experience_scope_invalid")
    if interpretation is not None and (
        interpretation.target_ref != source.target_id
        or interpretation.new_evidence_refs != (source.key,)
    ):
        raise ValueError("relationship_interpretation_source_mismatch")
    receipt = db.scalar(select(RelationshipExperienceReceipt).where(
        RelationshipExperienceReceipt.world_id == source.world_id,
        RelationshipExperienceReceipt.actor_world_character_id == source.actor_id,
        RelationshipExperienceReceipt.source_kind == source.kind,
        RelationshipExperienceReceipt.source_key == source.key,
    ))
    if receipt is not None:
        if receipt.target_world_character_id != source.target_id:
            raise ValueError("relationship_experience_target_changed")
        return db.scalar(select(RelationshipMetricApplication).where(RelationshipMetricApplication.experience_id == receipt.id))
    receipt = RelationshipExperienceReceipt(id=uuid7_string(), world_id=source.world_id,
        actor_world_character_id=source.actor_id, target_world_character_id=source.target_id,
        source_kind=source.kind, source_key=source.key, source_revision=source.revision,
        occurred_at=source.occurred_at, delivered_at=source.delivered_at)
    db.add(receipt)
    db.flush()
    payload = None if interpretation is None else asdict(interpretation)
    if payload:
        payload["new_evidence_refs"] = list(payload["new_evidence_refs"])
    application = RelationshipMetricApplication(id=uuid7_string(), experience_id=receipt.id,
        decision_key=decision_key, status="pending", proposal={"interpretation": payload, "timezone": source.timezone, "metadata_status": metadata_status})
    db.add(application)
    db.flush()
    return application


def apply_staged_experience(db: Session, *, application_id: str, references: ExperienceReferences,
                            now: datetime) -> RelationshipMetricApplication:
    """Call at a safe boundary. Receipt, budget, state and outbox commit together."""
    app = db.scalar(select(RelationshipMetricApplication).where(RelationshipMetricApplication.id == application_id).with_for_update())
    if app is None:
        raise ValueError("relationship_application_not_found")
    if app.status != "pending":
        return app
    # Acquire a database write fence before reading shared state/budget (SQLite
    # ignores SELECT FOR UPDATE; PostgreSQL also retains the row lock).
    claimed = db.execute(update(RelationshipMetricApplication).where(
        RelationshipMetricApplication.id == app.id, RelationshipMetricApplication.status == "pending"
    ).values(status="pending"))
    if claimed.rowcount != 1:
        db.refresh(app)
        return app
    receipt = db.get(RelationshipExperienceReceipt, app.experience_id)
    if receipt is None:
        raise ValueError("relationship_experience_not_found")
    source = ExperiencedSource(receipt.world_id, receipt.actor_world_character_id, receipt.target_world_character_id,
        receipt.source_kind, receipt.source_key, receipt.source_revision, receipt.occurred_at, receipt.delivered_at,
        app.proposal["timezone"])
    references.validate(source)
    policy = interpreted_policy(db, source.world_id)
    if policy is None or _utc(source.occurred_at) < _utc(policy.activated_at):
        app.status = "superseded"
        return app
    raw = app.proposal.get("interpretation")
    interpretation = None
    if raw is not None:
        parsed = parse_metric_interpretations([raw], max_targets=1)
        if parsed.status != "valid":
            app.status = "invalid"
            return app
        interpretation = parsed.interpretations[0]
    state = _relationship_state(db, world_id=source.world_id, actor_world_character_id=source.actor_id,
                                target_world_character_id=source.target_id)
    db.refresh(state)
    day = _utc(source.delivered_at).astimezone(ZoneInfo(source.timezone)).date()
    identity = (source.world_id, source.actor_id, source.target_id, day)
    budget = db.get(RelationshipMetricBudget, identity, with_for_update=True, populate_existing=True)
    if budget is None:
        budget = RelationshipMetricBudget(world_id=source.world_id, actor_world_character_id=source.actor_id,
            target_world_character_id=source.target_id, local_day=day, usage={})
        db.add(budget)
    result = calculate_metric_delta({axis: getattr(state, axis) for axis in ("familiarity", "affinity", "trust", "tension")},
                                    budget.usage, new_contact=True, interpretation=interpretation)
    for axis, value in result.values.items():
        setattr(state, axis, value)
    budget.usage = result.usage
    state.interaction_count += 1
    state.version += 1
    state.last_metric_at = now
    state.updated_at = now
    app.status = "applied"
    app.actual_delta = result.deltas
    app.state_version = state.version
    app.applied_at = now
    db.flush()
    enqueue_snapshot(db, state)
    return app
