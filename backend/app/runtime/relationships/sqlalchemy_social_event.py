"""Runtime SQLAlchemy adapter for canonical social-event and relationship writes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from hashlib import sha256
import json
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.core.ids import uuid7_string
from app.domains.relationships.models.social import (
    SOCIAL_EVENT_TYPES,
)
from app.domains.relationships.exceptions import (
    SocialEventRuntimeError,
)
from app.domains.relationships.constants import (
    SOCIAL_EVENT_SCHEMA_VERSION,
    GRAPH_PAYLOAD_VERSION,
    SOURCE_EXCLUSION_PAYLOAD_VERSION,
    _RELATION_EVENT_TYPES,
)
from app.domains.relationships.contracts.events import (
    EvidenceInput,
    EventApplyResult,
    _Delta,
)
from app.domains.relationships.policies.events import (
    _aware_utc,
    _world_zone,
    _local_day_bounds,
    _snapshot,
    _clamp,
    _purpose_delta,
    _delta,
)
from app.domains.relationships.service.state import (
    _relationship_state,
    _delta_is_capped,
)
from app.domains.relationships.service.projection_events import (
    _enqueue_outbox,
    _enqueue_source_exclusion_outbox,
)
from app.domains.relationships.service.events import (
    exclude_events_for_posts,
)


from app.domains.social.repository.blocks import world_character_pair_is_blocked
from app.domains.relationships.service.events import record_successful_social_event as record_event
from app.runtime.relationships.event_references import SqlAlchemyEventReferences


def record_successful_social_event(
    db: Session,
    *,
    world_id: str,
    actor_world_character_id: str,
    target_world_character_id: str | None,
    event_type: str,
    occurred_at: datetime,
    idempotency_key: str,
    evidence: EvidenceInput,
) -> EventApplyResult:
    return record_event(
        db, references=SqlAlchemyEventReferences(db), world_id=world_id,
        actor_world_character_id=actor_world_character_id,
        target_world_character_id=target_world_character_id, event_type=event_type,
        occurred_at=occurred_at, idempotency_key=idempotency_key, evidence=evidence,
    )
