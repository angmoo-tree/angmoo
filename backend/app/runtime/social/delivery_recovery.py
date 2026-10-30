"""Persist the existing public-action draft and its bounded DB-only budget."""
from datetime import UTC, datetime, timedelta
from random import uniform
import json
from app.core.activity_transactions import activity_write
from app.domains.routines.models.resident import AgentPublicActionExecution as Execution


class DeliveryStorageWait(RuntimeError):
    def __init__(self, seconds):
        super().__init__("activity_storage_retry_wait")
        self.seconds = max(0, seconds)


class DeliveryRecoveryRequired(RuntimeError):
    pass


def begin(db, execution_id, *, action, writing):
    if db.in_transaction():
        db.rollback()
    def write():
        row = db.get(Execution, execution_id, populate_existing=True)
        saved = dict((row.result or {}).get("_delivery", {}))
        now = datetime.now(UTC)
        if row.status == "succeeded":
            return
        if saved.get("next_at") and datetime.fromisoformat(saved["next_at"]) > now:
            raise DeliveryStorageWait((datetime.fromisoformat(saved["next_at"])-now).total_seconds())
        first = datetime.fromisoformat(saved.get("first_at", now.isoformat()))
        if saved.get("rounds", 0) >= 3 or (now-first).total_seconds() >= 120:
            raise DeliveryRecoveryRequired("activity_storage_retry_exhausted")
        payload = json.loads(json.dumps({"action": action, "writing": writing}, default=str))
        if saved.get("payload", payload) != payload:
            raise DeliveryRecoveryRequired("activity_received_draft_changed")
        saved.update(rounds=saved.get("rounds", 0)+1, first_at=first.isoformat(), next_at=None)
        saved.setdefault("payload", payload)
        row.result = {"_delivery": saved}
        row.status = "pending"
    activity_write(db, write, require_clean=True)


def defer(db, execution_id, *, unknown=False):
    db.rollback()
    def write():
        row = db.get(Execution, execution_id, populate_existing=True)
        if row.status == "succeeded":
            return None
        saved = dict((row.result or {}).get("_delivery", {}))
        count = saved.get("rounds", 3)
        first = datetime.fromisoformat(saved.get("first_at", datetime.now(UTC).isoformat()))
        delay = (5, 15)[count-1]+uniform(0, 1) if count < 3 else 0
        attention = unknown or count >= 3 or (datetime.now(UTC)-first).total_seconds()+delay >= 120
        saved["next_at"] = None if attention else (datetime.now(UTC)+timedelta(seconds=delay)).isoformat()
        row.result, row.status = {"_delivery": saved}, "storage_attention" if attention else "storage_retry_wait"
        row.failure_class = "storage_outcome_unknown" if unknown else "storage_retry_exhausted" if attention else "storage_retry_wait"
        return None if attention else delay
    return activity_write(db, write, require_clean=True)
