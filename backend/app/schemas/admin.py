from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AdminMutationNote(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class AdminOperationBannerRead(BaseModel):
    key: Literal["agent_activity_info", "agent_activity_maintenance"]
    enabled: bool
    title: str
    message: str
    blocks_auto_ticks: bool = False
    blocks_run_now: bool = False
    blocks_feed_cues: bool = False
    updated_by_user_id: str | None = None
    updated_at: datetime | None = None


class AdminOperationBannerUpdate(BaseModel):
    enabled: bool
    title: str = Field(default="", max_length=160)
    message: str = Field(default="", max_length=2000)
    blocks_auto_ticks: bool = False
    blocks_run_now: bool = False
    blocks_feed_cues: bool = False
    note: str | None = Field(default=None, max_length=1000)


AdminFreeImageModel = Literal["flux", "zimage", "sana", "replicate-zimage-turbo-lora"]
AdminPollinationsImageRouteMode = Literal["direct", "lambda"]
AdminPollinationsDiagnosticModel = Literal["flux", "zimage"]


class AdminFreeImageModelOptionRead(BaseModel):
    model: AdminFreeImageModel
    label: str


class AdminFreeImageModelRead(BaseModel):
    model: AdminFreeImageModel
    label: str
    options: list[AdminFreeImageModelOptionRead]
    updated_by_user_id: str | None = None
    updated_at: datetime | None = None


class AdminFreeImageModelUpdate(BaseModel):
    model: AdminFreeImageModel
    note: str | None = Field(default=None, max_length=1000)


class AdminPollinationsImageRouteOptionRead(BaseModel):
    mode: AdminPollinationsImageRouteMode
    label: str


class AdminPollinationsImageRouteRead(BaseModel):
    mode: AdminPollinationsImageRouteMode
    label: str
    source: Literal["db", "env", "default"]
    relay_configured: bool
    options: list[AdminPollinationsImageRouteOptionRead]
    updated_by_user_id: str | None = None
    updated_at: datetime | None = None


class AdminPollinationsImageRouteUpdate(BaseModel):
    mode: AdminPollinationsImageRouteMode
    note: str | None = Field(default=None, max_length=1000)


class AdminProfileImageGenerationRead(BaseModel):
    enabled: bool
    key_configured: bool
    model: AdminFreeImageModel
    model_label: str
    provider: Literal["pollinations", "replicate"]
    model_source: Literal["db", "env", "default"]
    model_options: list[AdminFreeImageModelOptionRead]
    route_mode: AdminPollinationsImageRouteMode
    route_label: str
    effective_route_mode: Literal["direct", "lambda", "replicate"]
    effective_route_label: str
    route_source: Literal["db", "env", "default"]
    route_options: list[AdminPollinationsImageRouteOptionRead]
    relay_configured: bool
    translator_configured: bool
    model_updated_by_user_id: str | None = None
    model_updated_at: datetime | None = None
    route_updated_by_user_id: str | None = None
    route_updated_at: datetime | None = None


class AdminProfileImageModelUpdate(BaseModel):
    model: AdminFreeImageModel
    note: str | None = Field(default=None, max_length=1000)


class AdminProfileImageRouteUpdate(BaseModel):
    mode: AdminPollinationsImageRouteMode
    note: str | None = Field(default=None, max_length=1000)


class AdminPollinationsImageDirectProbeRead(BaseModel):
    ok: bool
    tested_at: datetime
    content_type: str | None = None
    byte_size: int | None = None
    elapsed_ms: int
    status_code: int | None = None
    failure_class: str | None = None
    response_body_preview: str | None = None
    prompt_length: int
    url_length: int | None = None


class AdminPollinationsImageDiagnosticProbeCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    model: AdminPollinationsDiagnosticModel = "zimage"
    route_mode: AdminPollinationsImageRouteMode = "lambda"
    note: str | None = Field(default=None, max_length=1000)


class AdminPollinationsImageDiagnosticProbeAttemptRead(BaseModel):
    ok: bool
    safe_filter: str | None = None
    content_type: str | None = None
    byte_size: int | None = None
    elapsed_ms: int
    status_code: int | None = None
    failure_class: str | None = None
    diagnostic_hint: str | None = None
    response_body_preview: str | None = None
    prompt_length: int
    url_length: int | None = None
    relay_elapsed_ms: int | None = None


class AdminPollinationsImageDiagnosticProbeRead(BaseModel):
    classification: str
    tested_at: datetime
    model: AdminPollinationsDiagnosticModel
    route_mode: AdminPollinationsImageRouteMode
    prompt_hash: str
    prompt_length: int
    safe_on: AdminPollinationsImageDiagnosticProbeAttemptRead
    safe_off: AdminPollinationsImageDiagnosticProbeAttemptRead


class AdminAgentActivityNoticesRead(BaseModel):
    info: AdminOperationBannerRead
    maintenance: AdminOperationBannerRead


class AdminTreeNoticeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=4000)
    note: str | None = Field(default=None, max_length=1000)


class AdminTreeNoticeUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=4000)
    note: str | None = Field(default=None, max_length=1000)


class AdminTreeNoticeRead(BaseModel):
    id: str
    title: str
    body: str
    author_user_id: str
    author_display_name: str
    hidden_at: datetime | None = None
    comment_count: int = 0
    created_at: datetime
    updated_at: datetime


class AdminTreeNoticeListRead(BaseModel):
    items: list[AdminTreeNoticeRead]


class AdminReportPostRead(BaseModel):
    id: str
    post_type: str
    title: str
    body: str
    author_user_id: str | None = None
    author_character_id: str | None = None
    author_name: str
    report_count: int
    reason_counts: dict[str, int]
    report_hidden_at: datetime | None = None
    deleted_at: datetime | None = None
    created_at: datetime


class AdminReportQueueRead(BaseModel):
    items: list[AdminReportPostRead]


class AdminCharacterRead(BaseModel):
    id: str
    owner_id: str
    name: str
    handle: str
    status: str
    moderation_status: str
    moderation_reason: str | None = None
    moderation_note: str | None = None
    auto_enabled: bool
    assigned_slot_status: str | None = None
    report_related_post_count: int = 0
    last_run_status: str | None = None
    last_run_at: datetime | None = None


class AdminCharacterListRead(BaseModel):
    items: list[AdminCharacterRead]


class AdminCharacterModerationUpdate(BaseModel):
    reason: str = Field(default="policy_violation", max_length=80)
    note: str | None = Field(default=None, max_length=1000)


class AdminRunSummaryRead(BaseModel):
    id: str
    character_id: str
    agent_id: str
    status: str
    failure_class: str | None = None
    state_failure_class: str | None = None
    planner_error_count: int = 0
    public_action_count: int = 0
    llm_call_count: int | None = None
    llm_generate_call_count: int | None = None
    llm_embedding_call_count: int | None = None
    provider_call_count: int | None = None
    created_at: datetime
    completed_at: datetime | None = None


class AdminRunListRead(BaseModel):
    items: list[AdminRunSummaryRead]


class AdminAuditLogRead(BaseModel):
    id: int
    admin_user_id: str
    action: str
    target_type: str
    target_id: str
    note: str | None = None
    metadata: dict[str, Any] | None = None
    request_ip: str | None = None
    user_agent: str | None = None
    created_at: datetime


class AdminAuditLogListRead(BaseModel):
    items: list[AdminAuditLogRead]


class AdminOverviewRead(BaseModel):
    window_hours: int
    run_count: int
    failed_run_count: int
    public_action_count: int
    report_queue_count: int
    suspended_character_count: int
    info_banner_enabled: bool
    maintenance_banner_enabled: bool
