"""Versioned local connection transitions; a client ID never authenticates APIs."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domains.identity.schemas_environment import EnvironmentReport

LOCAL_AUTH_PROTOCOL = 2


class LocalClientRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol: Literal[2]
    installation_id: str = Field(min_length=1, max_length=64)
    client_instance_id: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    expected_generation: int = Field(ge=0)


class LocalPrepareRequest(LocalClientRequest):
    preferred_language: str | None = Field(default=None, max_length=80)

    @field_validator("preferred_language")
    @classmethod
    def language(cls, value):
        return EnvironmentReport.language(value)


class LocalClientQuery(LocalClientRequest):
    # URL query values are strings. Parse the integer before enforcing v2;
    # Literal[2] is appropriate for JSON but does not coerce query "2".
    protocol: int = Field(ge=LOCAL_AUTH_PROTOCOL, le=LOCAL_AUTH_PROTOCOL)


class LocalClaimRequest(LocalClientRequest):
    owner_user_id: str = Field(min_length=1, max_length=64)
    local_label: str | None = Field(default=None, max_length=80)


class LocalClientRead(BaseModel):
    protocol: Literal[2] = LOCAL_AUTH_PROTOCOL
    installation_id: str
    client_instance_id: str
    generation: int
    state: Literal["active", "stopped"]


class LocalLabelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    local_label: str | None = Field(default=None, max_length=80)
