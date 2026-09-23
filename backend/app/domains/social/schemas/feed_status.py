"""Read-only readiness and explicit, scope-bound Feed execution diagnostics."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class FeedReadinessRead(BaseModel):
    state: Literal["ready", "blocked", "disabled", "unsupported"]
    reason_code: str | None = None
    persona_changed: bool = False
    checked_at: datetime


class FeedAttemptRead(BaseModel):
    run_id: str
    occurred_at: datetime
    result: str
    reason_code: str | None = None
    candidate_count: int | None = Field(default=None, ge=0)
    delivered_count: int | None = Field(default=None, ge=0)
    delivery_state: Literal["prepared", "dispatched", "uncertain", "delivered"] | None = None


class FeedStatusRead(BaseModel):
    readiness: FeedReadinessRead
    last_attempt: FeedAttemptRead | None = None
