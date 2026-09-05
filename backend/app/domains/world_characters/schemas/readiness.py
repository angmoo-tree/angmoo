"""Readiness response shared by character settings and resident execution."""
from typing import Literal
from pydantic import BaseModel


class AgentActivityProfileReadinessRead(BaseModel):
    ready: bool
    source: Literal["legacy_tendency", "world_community_profile"]
    reason_code: str | None = None
    world_id: str | None = None
    world_character_id: str | None = None
