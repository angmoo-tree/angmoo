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


class ProposalPost(Protocol):
    id: str
    world_id: str | None
    author_world_character_id: str | None
    deleted_at: datetime | None
    report_hidden_at: datetime | None
    visibility: str
    reply_to_post_id: str | None


class ProposalCharacter(Protocol):
    role_key: str | None


class ProposalWorld(Protocol):
    timezone: str


class ProposalPreview(Protocol):
    source_post_id: str
    target_world_character_id: str
    place_key: str | None
    target_daypart: str
    date_policy: str
    target_date: date | None
    text: str
    activity_seed: str


class ProposalScheduledJoint(Protocol):
    joint_activity: ProposalJoint


class ProposalReferences(Protocol):
    """Actual related-owner operations, preserving caller Session and error types."""
    def get_post(self, post_id: str) -> ProposalPost | None: ...
    def get_world(self, world_id: str) -> ProposalWorld | None: ...
    def validate_pair(self, *, world_id: str, first_world_character_id: str, second_world_character_id: str) -> tuple[ProposalCharacter, ProposalCharacter]: ...
    def validate_place(self, *, world_id: str, place_key: str | None, target_daypart: str, participant_role_keys: tuple[str | None, str | None]) -> None: ...
    def active_commitment_count(self, *, world_character_id: str) -> int: ...
    def slot_available(self, *, world_id: str, world_character_id: str, local_date: date, daypart: str, now: datetime) -> bool: ...
    def create_scheduled_joint(self, *, proposal: models.ActivityProposal, acceptance_event_id: str, scheduled_local_date: date, scheduled_start_at: datetime, scheduled_end_at: datetime, timezone_name: str, now: datetime) -> ProposalScheduledJoint: ...
    def find_joint_for_proposal(self, proposal_id: str) -> ProposalJoint | None: ...
    def local_activity_date(self, now: datetime, timezone_name: str) -> date: ...
    def daypart_windows(self, local_date: date, timezone_name: str) -> dict[str, tuple[datetime, datetime]]: ...
