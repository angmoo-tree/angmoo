from __future__ import annotations

import json

from app.core.redaction import redact_exact_secret_text
from app.providers.contracts import (
    EmbeddingRequest,
    ProviderCapabilities,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
)


class FakeProviderAdapter:
    capabilities = ProviderCapabilities(
        text=True,
        structured_json=True,
        image_input=True,
        embedding=True,
    )

    def __init__(self, scenario: str = "success") -> None:
        self.scenario = scenario

    async def generate_text(self, request: ProviderRequest) -> ProviderResponse:
        return self._response(request, structured=False)

    async def generate_json(self, request: ProviderRequest) -> ProviderResponse:
        return self._response(request, structured=True)

    async def embed(self, request: EmbeddingRequest) -> list[float]:
        self._raise_for_failure()
        return [0.0] * request.output_dimension

    def normalize_error(
        self, exc: BaseException, *, api_key: str | None = None
    ) -> ProviderError:
        message = redact_exact_secret_text(str(exc), api_key)
        if isinstance(exc, ProviderError):
            return ProviderError(
                message,
                failure_class=exc.failure_class,
                provider_status=exc.provider_status,
                provider_code=exc.provider_code,
                retryable=exc.retryable,
                retry_after=exc.retry_after,
            )
        return ProviderError(
            message,
            failure_class=type(exc).__name__,
            retryable=isinstance(exc, TimeoutError),
        )

    def _response(
        self, request: ProviderRequest, *, structured: bool
    ) -> ProviderResponse:
        self._raise_for_failure()
        if self.scenario == "invalid_json":
            return ProviderResponse(
                text="{invalid-json",
                parsed=None,
                usage=ProviderUsage(input_tokens=1, output_tokens=1, total_tokens=2),
            )
        payload = {"status": "ok", "model": request.model}
        return ProviderResponse(
            text=json.dumps(payload) if structured else "fake provider response",
            parsed=payload if structured else None,
            usage=ProviderUsage(input_tokens=1, output_tokens=1, total_tokens=2),
            finish_reason="STOP",
        )

    def _raise_for_failure(self) -> None:
        if self.scenario == "timeout":
            raise TimeoutError("fake provider timeout")
        if self.scenario == "rate_limit":
            raise ProviderError(
                "fake provider rate limit",
                failure_class="rate_limit",
                provider_status="RESOURCE_EXHAUSTED",
                provider_code=429,
                retryable=True,
            )
        if self.scenario == "unsupported":
            raise ProviderError(
                "fake provider unsupported capability",
                failure_class="unsupported_capability",
                retryable=False,
            )
        if self.scenario not in {"success", "invalid_json"}:
            raise ValueError(f"unknown fake provider scenario: {self.scenario}")
