from pydantic import BaseModel, ConfigDict, Field


class WorldInstanceDelete(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: int = Field(ge=1)
    confirmed_name: str = Field(min_length=1, max_length=80)
    consent: bool

class WorldInstanceDeleteRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: str
    world_id: str
    world_character_id: str
    deleted: bool
    public_material_preserved: bool
    private_memory_count: int = Field(ge=0)
