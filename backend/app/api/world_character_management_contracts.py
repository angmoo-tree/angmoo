"""HTTP composition of World target identity and the existing Routine run DTO."""
from typing import Literal
from pydantic import BaseModel
from app.domains.routines.schemas.runs import OpenClawAgentRunRead


class WorldCharacterRunNowRead(BaseModel):
    contract_version: Literal["world-character-run-now-v1"] = "world-character-run-now-v1"
    world_id: str
    world_character_id: str
    character_id: str
    revision: int
    run: OpenClawAgentRunRead
