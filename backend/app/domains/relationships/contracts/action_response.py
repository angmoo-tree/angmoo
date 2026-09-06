"""Published-action proposal response values in their original attached transaction."""

from dataclasses import dataclass
from datetime import date
from typing import Protocol
from app.domains.relationships import models
from app.domains.relationships.contracts.proposals import ResolvedSchedule


@dataclass(frozen=True)
class ProposalResponseInput:
    proposal_id: str
    decision: str
    counter_activity_seed: str | None = None
    counter_place_key: str | None = None
    counter_target_daypart: str | None = None
    counter_date_policy: str | None = None
    counter_target_date: date | None = None


@dataclass(frozen=True)
class PreparedProposalResponse:
    proposal: models.ActivityProposal
    response: ProposalResponseInput
    resolved_schedule: ResolvedSchedule | None


class ProposalResponseActor(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def world_id(self) -> str: ...
