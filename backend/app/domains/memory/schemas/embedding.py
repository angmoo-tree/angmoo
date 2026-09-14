from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from app.domains.memory.schemas import MemoryScopeRead


class MemoryEmbeddingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    enabled: bool
    provider: str = Field(default="google", max_length=40)
    model: str = Field(default="gemini-embedding-2", max_length=120)
    credential_id: str | None = Field(default=None, min_length=1, max_length=64)


class MemoryEmbeddingCredentialOption(BaseModel):
    id: str
    label: str


class MemoryEmbeddingRead(BaseModel):
    scope: MemoryScopeRead
    enabled: bool
    provider: str
    model: str
    credential_id: str | None
    profile: str
    version: int
    ready: bool
    reason_code: str | None
    available_credentials: list[MemoryEmbeddingCredentialOption] = Field(default_factory=list)
    runtime_status: Literal["unknown", "stopped", "ready", "recovering", "degraded", "vector_unavailable"] = "unknown"
