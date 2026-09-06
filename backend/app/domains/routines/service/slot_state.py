from __future__ import annotations

from app.domains.routines import models
from app.domains.routines.constants import SLOT_STATUS_EMPTY


def _clear_resident_slot(slot: models.AgentSlot) -> None:
    slot.status = SLOT_STATUS_EMPTY
    slot.assigned_user_id = None
    slot.assigned_character_id = None
    slot.assigned_credential_id = None
    slot.next_tick_at = None
    slot.last_run_at = None
    slot.heartbeat_interval_seconds = None
    slot.locked_by_run_id = None
    slot.lease_expires_at = None
    slot.last_error = None
