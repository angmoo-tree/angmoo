"""Narrow protected POST DTOs; process and database identities remain private."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class SearchPreparationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchPreparationAxis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["disabled", "not_started", "preparing", "ready", "unavailable"]
    reason: str | None = Field(default=None, max_length=80, pattern=r"^[a-z0-9_]+$")


class SearchPreparationAxes(BaseModel):
    fts: SearchPreparationAxis
    vector: SearchPreparationAxis


class SearchPreparationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["memory-search-preparation.v1"]
    world_id: str
    thread_id: str
    axes: SearchPreparationAxes
