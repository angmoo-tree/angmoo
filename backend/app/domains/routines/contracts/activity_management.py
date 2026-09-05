"""Attached values and lazy collaborators used by activity management."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Protocol
from sqlalchemy.orm import Session
from app.domains.routines.contracts.activity_policy import ActivityTimezoneReader

class ActivityOwner(Protocol):
    id: str

class ActivityCharacter(Protocol):
    id: str

class InitialActivitySettings(Protocol):
    activity_interval_minutes: int | None
    active_hours_start: str | None
    active_hours_end: str | None

class TendencyPersona(Protocol):
    id: str
    name: str
    handle: str
    one_liner: str
    personality: str
    speech_style: str
    worldview: str
    topic_preferences: str
    safety_rules: str
    persona_summary: str



@dataclass(frozen=True)
class ActivityManagementReferences:
    get_owned_character: Callable[[Session, ActivityOwner, str], ActivityCharacter]
    ensure_mutable: Callable[[ActivityOwner], None]
    is_local_mode: Callable[[ActivityCharacter], bool]
    execution_mode_error: type[Exception]
    active_hours_error: type[Exception]
    local_mode_message: str
    timezone_reader: ActivityTimezoneReader
