from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.providers.registry import MESSAGE_GOOGLE_MODELS
from app.schemas.community import ProfileRef


MessageCredentialSource = Literal["message_key", "agent_key"]
MessageGoogleModel = Literal[*MESSAGE_GOOGLE_MODELS]


class CharacterMessageSettingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    character_id: str
    enabled: bool = False


class CharacterMessageSettingUpdate(BaseModel):
    enabled: bool


class MessageSettingsRead(BaseModel):
    credential_source: MessageCredentialSource = "message_key"
    source_character_id: str | None = None
    default_model: MessageGoogleModel = "gemini-2.5-flash-lite"
    message_key_fingerprint: str | None = None
    agent_key_fingerprint: str | None = None
    has_usable_key: bool = False
    owned_agents: list[ProfileRef] = Field(default_factory=list)


class MessageSettingsUpdate(BaseModel):
    credential_source: MessageCredentialSource | None = None
    source_character_id: str | None = Field(default=None, max_length=64)
    default_model: MessageGoogleModel | None = None
    api_key: str | None = Field(default=None, min_length=1, max_length=4000)
    clear_message_key: bool = False

    @model_validator(mode="after")
    def validate_source_character(self) -> "MessageSettingsUpdate":
        if self.credential_source == "agent_key" and not self.source_character_id:
            raise ValueError("source_character_id is required for agent key reuse.")
        return self


class MessageThreadCreate(BaseModel):
    character_id: str = Field(min_length=1, max_length=64)
    selected_model: MessageGoogleModel | None = None


class MessageThreadUpdate(BaseModel):
    selected_model: MessageGoogleModel


class MessageMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class MessageMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thread_id: str
    role: Literal["user", "assistant"]
    content: str
    model: str | None = None
    status: Literal["ok", "error"]
    error_code: str | None = None
    created_at: datetime


class MessageThreadRead(BaseModel):
    id: str
    requester: ProfileRef
    character: ProfileRef
    selected_model: str
    last_message_at: datetime | None = None
    created_at: datetime
    latest_message: MessageMessageRead | None = None
    messages: list[MessageMessageRead] = Field(default_factory=list)


class MessageThreadListRead(BaseModel):
    items: list[MessageThreadRead]
    max_threads: int = 5


class MessageSendRead(BaseModel):
    thread: MessageThreadRead
    user_message: MessageMessageRead
    assistant_message: MessageMessageRead
