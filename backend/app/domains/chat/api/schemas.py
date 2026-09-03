"""Stable HTTP schemas for the legacy-compatible Chat v1 API.

The wire contract is intentionally unchanged in P8-L-B.  These schemas move
under the Chat domain so routes no longer depend on the horizontal schema
aggregate. P8-L-D adds explicit World-scoped read DTOs alongside the preserved
legacy wire contract; it does not alter legacy request payloads.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.profile_ref import ProfileRef
from app.domains.chat.domain.model_binding import MessageModelBindingMode
from app.providers.registry import MESSAGE_GOOGLE_MODELS


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
    model_binding_mode: MessageModelBindingMode = (
        MessageModelBindingMode.THREAD_OVERRIDE
    )
    last_message_at: datetime | None = None
    created_at: datetime
    latest_message: MessageMessageRead | None = None
    messages: list[MessageMessageRead] = Field(default_factory=list)
    world_id: str | None = None
    requester_world_character_id: str | None = None
    responding_world_character_id: str | None = None
    world_scope_status: Literal["resolved", "ambiguous", "quarantined"] = "ambiguous"


class MessageThreadListRead(BaseModel):
    items: list[MessageThreadRead]
    max_threads: int = 5


class MessageSendRead(BaseModel):
    thread: MessageThreadRead
    user_message: MessageMessageRead
    assistant_message: MessageMessageRead


class WorldChatThreadCreate(BaseModel):
    responding_world_character_id: str = Field(min_length=1, max_length=64)
    requester_world_character_id: str | None = Field(
        default=None, min_length=1, max_length=64
    )
    selected_model: MessageGoogleModel | None = None


class WorldChatRoleRead(BaseModel):
    world_character_id: str
    character_id: str
    display_name: str
    handle: str | None = None
    avatar_url: str | None = None
    banner_url: str | None = None
    role_key: str | None = None
    control_mode: Literal["autonomous", "owner_controlled"]
    profile_capability: Literal["available"] = "available"


class WorldChatEntryRead(BaseModel):
    schema_version: Literal["world-chat-entry-v1"] = "world-chat-entry-v1"
    world_id: str
    responding: WorldChatRoleRead
    requester_cardinality: Literal["zero", "one", "anomaly"]
    requester: WorldChatRoleRead | None = None
    create_or_get_capability: Literal["available", "unavailable"]
    disabled_reason: Literal[
        "requester_missing",
        "requester_cardinality_anomaly",
        "self_target",
        "blocked",
        "target_not_chat_capable",
    ] | None = None


class WorldChatThreadRead(BaseModel):
    id: str
    world_id: str
    requester: WorldChatRoleRead
    responding: WorldChatRoleRead
    selected_model: MessageGoogleModel
    default_model: MessageGoogleModel
    model_binding_mode: MessageModelBindingMode
    last_message_at: datetime | None = None
    created_at: datetime
    latest_message: MessageMessageRead | None = None
    messages: list[MessageMessageRead] = Field(default_factory=list)
    evidence_summaries: list["WorldChatEvidenceSummaryRead"] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_resolved_model(self) -> "WorldChatThreadRead":
        if (
            self.model_binding_mode is MessageModelBindingMode.DEFAULT
            and self.selected_model != self.default_model
        ):
            raise ValueError("default-bound World Chat model is not resolved")
        return self


class WorldChatThreadListRead(BaseModel):
    items: list[WorldChatThreadRead]
    ambiguous_legacy_count: int = 0
    max_threads: int = 5


class WorldChatThreadCreateRead(BaseModel):
    outcome: Literal["created", "reused", "resolution_required"]
    thread: WorldChatThreadRead | None = None
    resolution_code: Literal[
        "requester_missing", "requester_cardinality_anomaly"
    ] | None = None


class WorldChatThreadModelUpdate(BaseModel):
    mode: MessageModelBindingMode
    selected_model: MessageGoogleModel | None = None

    @model_validator(mode="after")
    def validate_binding(self) -> "WorldChatThreadModelUpdate":
        if self.mode is MessageModelBindingMode.DEFAULT:
            if self.selected_model is not None:
                raise ValueError("default binding cannot include selected_model")
            return self
        if self.selected_model is None:
            raise ValueError("thread_override requires selected_model")
        return self


class WorldChatMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=16, max_length=160)


class WorldChatRetryCreate(BaseModel):
    failed_request_id: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=16, max_length=160)


class WorldChatGenerationRequestRead(BaseModel):
    protocol_version: Literal["chat-generation-stream.v1"] = (
        "chat-generation-stream.v1"
    )
    request_id: str
    request_scope_hash: str
    generation_id: str
    attempt_number: int
    response_slot_id: str
    state: str
    route: str | None = None
    retryable: bool = False
    failure_class: str | None = None
    last_accepted_sequence: int = -1
    user_message: MessageMessageRead
    assistant_message: MessageMessageRead | None = None
    response_metadata: dict[str, Any] = Field(default_factory=dict)


class WorldChatEvidenceSummaryRead(BaseModel):
    request_id: str
    assistant_message_id: int
    capability: Literal["available", "degraded"]
    count: int = Field(ge=1, le=12)


class WorldChatEvidenceItemRead(BaseModel):
    reference: str
    kind: Literal["canonical_source", "graph_relationship", "graph_event"]
    label: str
    excerpt: str | None
    occurred_at: datetime | None
    availability: Literal["available", "deleted", "unavailable"]
    related_character: str | None = None
    direction: Literal["incoming", "outgoing", "contextual"] | None = None
    canonical_href: str | None = None


class WorldChatEvidenceRead(BaseModel):
    schema_version: Literal["world-chat-evidence.v1"] = "world-chat-evidence.v1"
    request_id: str
    route: str
    retrieval_outcome: str
    capability: Literal["available", "degraded"]
    items: list[WorldChatEvidenceItemRead]


class WorldChatMessageAcceptRead(BaseModel):
    outcome: Literal["accepted", "replayed"]
    user_message: MessageMessageRead
    response_request: WorldChatGenerationRequestRead


class WorldChatLatestRequestRead(BaseModel):
    response_request: WorldChatGenerationRequestRead | None = None
