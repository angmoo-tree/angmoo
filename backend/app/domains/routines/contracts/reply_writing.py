"""Proposal response meaning shared by social judgement and reply writing."""
from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

RESPONSE_FIELDS = frozenset({"proposal_decision", "counter_activity_seed", "counter_place_key",
    "counter_target_daypart", "counter_date_policy", "counter_target_date"})


class ProposalResponseMeaning(BaseModel):
    proposal_decision: Literal["accept", "reject", "counter"] | None = None
    counter_activity_seed: str | None = Field(default=None, max_length=500)
    counter_place_key: str | None = Field(default=None, max_length=64)
    counter_target_daypart: Literal["dawn", "morning", "afternoon", "evening"] | None = None
    counter_date_policy: Literal["exact", "earliest_available"] | None = None
    counter_target_date: date | None = None

    @model_validator(mode="after")
    def validate_counter_contract(self) -> Self:
        values = [getattr(self, field) for field in RESPONSE_FIELDS if field != "proposal_decision"]
        if self.proposal_decision != "counter":
            if any(value is not None for value in values):
                raise ValueError("counter fields require proposal_decision=counter")
        elif (not self.counter_activity_seed or self.counter_target_daypart is None
                or self.counter_date_policy is None
                or (self.counter_date_policy == "exact" and self.counter_target_date is None)):
            raise ValueError("counter response fields are incomplete")
        return self


class ReplyTaskText(ProposalResponseMeaning):
    task_id: str = Field(min_length=1, max_length=180)
    body: str | None = Field(default=None, max_length=1000)
