from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderCapabilities:
    text: bool = False
    structured_json: bool = False
    image_input: bool = False
    embedding: bool = False


@dataclass(frozen=True)
class ProviderUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    call_type: str = "generate_content"
    duration_ms: int | None = None

    def as_direct_llm_usage(self) -> dict[str, int | None]:
        return {
            "prompt_token_count": self.input_tokens,
            "candidates_token_count": self.output_tokens,
            "total_token_count": self.total_tokens,
            "cached_content_token_count": self.cached_input_tokens,
        }


@dataclass(frozen=True)
class ProviderRequest:
    api_key: str = field(repr=False)
    model: str
    system_prompt: str
    user_prompt: str
    max_output_tokens: int
    timeout_seconds: float
    response_schema: Any | None = None
    response_mime_type: str | None = None
    thinking_level: str | None = None
    image_parts: tuple[Any, ...] = ()


@dataclass(frozen=True)
class EmbeddingRequest:
    api_key: str = field(repr=False)
    model: str
    text: str
    output_dimension: int


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    parsed: Any | None
    usage: ProviderUsage
    finish_reason: str | None = None


class ProviderError(Exception):
    def __init__(
        self,
        message: str,
        *,
        failure_class: str,
        provider_status: str | None = None,
        provider_code: int | str | None = None,
        retryable: bool = False,
        retry_after: datetime | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_class = failure_class
        self.provider_status = provider_status
        self.provider_code = provider_code
        self.retryable = retryable
        self.retry_after = retry_after


class ProviderAdapter(Protocol):
    capabilities: ProviderCapabilities

    async def generate_text(self, request: ProviderRequest) -> ProviderResponse: ...

    async def generate_json(self, request: ProviderRequest) -> ProviderResponse: ...

    def normalize_error(
        self, exc: BaseException, *, api_key: str | None = None
    ) -> ProviderError: ...


class EmbeddingAdapter(Protocol):
    capabilities: ProviderCapabilities

    async def embed(self, request: EmbeddingRequest) -> list[float]: ...

    def normalize_error(
        self, exc: BaseException, *, api_key: str | None = None
    ) -> ProviderError: ...
