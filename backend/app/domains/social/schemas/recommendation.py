from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class TopicDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=120)
    scope: Literal["common", "world"]


class TopicGenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topics: list[TopicDefinition] = Field(max_length=64)


class TopicRegenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=8, max_length=64)


class TopicKeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    world_character_id: str | None = None
