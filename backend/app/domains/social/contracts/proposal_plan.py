"""Validated proposal schedule; public text is supplied at the publishing boundary."""
from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


class ActivityProposalPlan(BaseModel):
    source_post_id: str
    activity_seed: str = Field(min_length=1, max_length=500)
    target_world_character_id: str
    place_key: str | None = Field(default=None, max_length=64)
    target_daypart: Literal["dawn", "morning", "afternoon", "evening"]
    date_policy: Literal["exact", "earliest_available"]
    target_date: date | None = None

    @model_validator(mode="after")
    def coherent_schedule(self) -> Self:
        if self.date_policy == "exact" and self.target_date is None:
            raise ValueError("exact proposal requires target_date")
        return self
