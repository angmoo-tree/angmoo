"""Proposal decisions and attached joint results shared by their caller workflows."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from app.domains.relationships import models


class ProposalJoint(Protocol):
    @property
    def id(self) -> str: ...


@dataclass(frozen=True)
class ProposalEligibility:
    eligible: bool
    reason_code: str | None
    target_world_character_id: str | None


@dataclass(frozen=True)
class ResolvedSchedule:
    local_date: date
    daypart: str
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    timezone_name: str


@dataclass(frozen=True)
class ProposalResponseResult:
    proposal: models.ActivityProposal
    child_proposal: models.ActivityProposal | None
    joint_activity: ProposalJoint | None
