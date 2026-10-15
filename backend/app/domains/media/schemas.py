from urllib.parse import urlsplit


def validate_profile_media_reference(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return ""
    parsed = urlsplit(trimmed)
    if (
        parsed.scheme
        or parsed.netloc
        or trimmed.startswith("//")
        or not parsed.path.startswith("/media/")
    ):
        raise ValueError("Profile media must use an Angmoo-managed media path.")
    return trimmed


from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class LegacyReferenceBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    character_id: str
    asset_id: str
    asset_revision: int
    asset_digest: str


class WorldGenerationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    appearance: str = Field(default="", max_length=1200)
    style: str = Field(default="", max_length=1200)
    negative: str = Field(default="", max_length=1800)
    reference_enabled: bool = False
    reference_asset_id: str | None = Field(default=None, max_length=64)
    reference_url: str | None = Field(default=None, max_length=500)
    legacy_reference: LegacyReferenceBinding | None = None
    profiles: dict = Field(default_factory=dict)


class WorldImagePolicyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    generation_limit: int | None = Field(default=None, ge=1, le=10000)
    vision_limit: int | None = Field(default=None, ge=1, le=10000)
    generation_enabled: bool | None = None
    vision_enabled: bool | None = None
    generation_settings: dict | None = None


class WorldImagePolicyRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    world_id: str
    world_character_id: str
    revision: int = Field(ge=1)
    generation_limit: int | None
    vision_limit: int | None
    generation_enabled: bool
    vision_enabled: bool
    generation_settings: dict
    generation_usage: int = Field(ge=0)
    vision_usage: int = Field(ge=0)
    timezone: str
    reset_at: datetime


from typing import Any, Literal
from pydantic import Field, model_validator
from .generation_contracts import StrictInput


class DiagnosticMessage(StrictInput):
    node_id: str | None = Field(default=None, max_length=2048)
    class_type: str | None = Field(default=None, max_length=2048)
    input_name: str | None = Field(default=None, max_length=2048)
    type: str | None = Field(default=None, max_length=2048)
    message: str | None = Field(default=None, max_length=2048)
    exception_type: str | None = Field(default=None, max_length=2048)
    exception_message: str | None = Field(default=None, max_length=2048)


class HttpDiagnostic(StrictInput):
    purpose: Literal["generation", "discovery", "result_download"]
    category: Literal["connect_timeout", "read_timeout", "write_timeout", "pool_timeout",
        "connect_error", "read_error", "write_error", "remote_protocol_error", "other_transport",
        "http_error", "result_invalid"]
    observed_phase: Literal["request_started", "response_headers", "response_body", "result_validation"]
    elapsed_ms: float = Field(ge=0, allow_inf_nan=False)
    headers_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    connect_timeout_s: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    read_timeout_s: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    write_timeout_s: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    pool_timeout_s: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    status: int | None = Field(default=None, ge=100, le=599)
    provider_code: Literal["400", "401", "402", "403", "408", "413", "422", "429", "500", "502", "503", "504",
        "rate_limit_exceeded", "insufficient_quota", "invalid_api_key", "invalid_request_error", "unknown"] | None = None
    request_id: str | None = Field(default=None, max_length=100, pattern=r"^(?:gen-[0-9]{1,20}-[A-Za-z0-9]{8,64}|[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12})$")
    completeness: Literal["no_body", "complete", "non_json", "truncated", "time_budget", "body_read_failed", "no_safe_fields"]


class ProviderDiagnostic(StrictInput):
    kind: Literal["error", "warning"]
    stage: Literal["submission", "execution", "history", "output"]
    messages: list[DiagnosticMessage] = Field(max_length=20)
    truncated: bool = False
    provider: Literal["comfyui", "openrouter", "nanogpt"] | None = None
    transport: HttpDiagnostic | None = None

    @model_validator(mode="after")
    def bounded(self):
        import json
        if len(json.dumps(self.model_dump(exclude_none=True), ensure_ascii=False).encode("utf-8")) > 16 * 1024:
            raise ValueError("comfy_diagnostic_too_large")
        return self


def diagnostic_projection(value):
    """Only the bounded public diagnostic contract may leave storage or enter it."""
    import json
    from pydantic import ValidationError
    try:
        if isinstance(value, str) and len(value.encode("utf-8")) > 16 * 1024:
            return None
        parsed = json.loads(value) if isinstance(value, str) else value
        return ProviderDiagnostic.model_validate(parsed).model_dump(exclude_none=True)
    except (ValidationError, ValueError, TypeError, RecursionError):
        return None


class TokenPosition(StrictInput):
    token: str
    role: str
    node_id: str
    input_name: str
    path: list[str | int]


class PreservedExpression(StrictInput):
    node_id: str
    input_name: str
    path: list[str | int]
    kind: Literal["preserved_expression"]


class WorkflowAnalysis(StrictInput):
    input_mode: Literal["placeholders", "node_bindings"]
    prompt: dict[str, dict[str, Any]]
    supported_tokens: dict[str, str]
    positions: list[TokenPosition]
    notices: list[PreservedExpression]
    used_roles: list[str]
    reference_required: bool
    prompt_applied: bool
    source_digest: str


class ImageGenerationJobRead(StrictInput):
    job_id: int | None
    post_id: str
    status: str
    reason: str | None
    attempt_count: int
    reference_source: str | None
    model: str | None
    cancellable: bool
    retryable: bool
    provider_diagnostic: ProviderDiagnostic | None = None
