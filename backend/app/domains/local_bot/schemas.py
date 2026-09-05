from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.core.response_schemas import UtcInstantResponseModel
from app.domains.characters.schemas import AgentExecutionMode

class AgentLocalConnectionRead(UtcInstantResponseModel):
    character_id: str
    execution_mode: AgentExecutionMode
    has_active_key: bool
    token_prefix: str | None = None
    last_used_at: datetime | None = None
    created_at: datetime | None = None
    revoked_at: datetime | None = None

class AgentLocalKeyCreateRead(BaseModel):
    connection: AgentLocalConnectionRead
    token: str

class BotCharacterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    handle: str
    avatar_url: str | None = None
    banner_url: str | None = None
    one_liner: str = ""
    status: str = "inactive"
    execution_mode: AgentExecutionMode = "local"

class BotMeRead(BaseModel):
    character: BotCharacterRead
