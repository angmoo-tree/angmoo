"""Existing external gates/read factories used by the same-Session slot request."""
from collections.abc import Callable
from dataclasses import dataclass
from sqlalchemy.orm import Session
from app.domains.routines.contracts.run_identity import RunIdentityReferences
from app.domains.routines.contracts.slots import SlotReferences
from app.domains.routines.contracts.activity_policy import ActivityTimezoneReader


@dataclass(frozen=True)
class SlotRequestWorkflows:
    identity_references: Callable[[], RunIdentityReferences]
    slot_references: Callable[[], SlotReferences]
    ensure_auto_ticks_available: Callable[[Session], None]
    ensure_run_now_available: Callable[[Session], None]
    timezone_reader: ActivityTimezoneReader
