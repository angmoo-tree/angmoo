from __future__ import annotations

import asyncio
from typing import Any

from google import genai
from google.genai import types

from app.core.redaction import redact_exact_secret_text
from app.providers.contracts import (
    EmbeddingRequest,
    ProviderCapabilities,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
)


def build_generate_content_config(
    *,
    system_prompt: str,
    max_output_tokens: int,
    response_mime_type: str | None,
    response_schema: Any | None,
    thinking_level: str | None,
) -> types.GenerateContentConfig:
    config_kwargs: dict[str, Any] = {
        "systemInstruction": system_prompt,
        "maxOutputTokens": max_output_tokens,
        "responseMimeType": response_mime_type,
        "responseSchema": response_schema,
    }
    if thinking_level:
        config_kwargs["thinkingConfig"] = types.ThinkingConfig(
            thinkingLevel=thinking_level
        )
    return types.GenerateContentConfig(**config_kwargs)


def _text_from_response(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()
    candidates = getattr(response, "candidates", None) or []
    parts: list[str] = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str) and part_text.strip():
                parts.append(part_text.strip())
    return "\n\n".join(parts).strip()


def _usage_from_response(response: Any) -> ProviderUsage:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return ProviderUsage()
    return ProviderUsage(
        input_tokens=getattr(usage, "prompt_token_count", None),
        output_tokens=getattr(usage, "candidates_token_count", None),
        total_tokens=getattr(usage, "total_token_count", None),
        cached_input_tokens=getattr(usage, "cached_content_token_count", None),
    )


def _finish_reason_from_response(response: Any) -> str | None:
    candidates = getattr(response, "candidates", None)
    if not candidates:
        return None
    finish_reason = getattr(candidates[0], "finish_reason", None)
    return str(finish_reason) if finish_reason is not None else None


def _generate_content_sync(request: ProviderRequest) -> ProviderResponse:
    client = genai.Client(
        api_key=request.api_key,
        http_options=types.HttpOptions(
            timeout=max(1, int(request.timeout_seconds * 1000))
        ),
    )
    config = build_generate_content_config(
        system_prompt=request.system_prompt,
        max_output_tokens=request.max_output_tokens,
        response_mime_type=request.response_mime_type,
        response_schema=request.response_schema,
        thinking_level=request.thinking_level,
    )
    contents: Any = request.user_prompt
    if request.image_parts:
        parts = [types.Part.from_text(text=request.user_prompt)]
        for image_part in request.image_parts:
            if image_part.data is not None:
                parts.append(
                    types.Part.from_bytes(
                        data=image_part.data,
                        mime_type=image_part.mime_type,
                    )
                )
            elif image_part.url:
                parts.append(
                    types.Part.from_uri(
                        file_uri=image_part.url,
                        mime_type=image_part.mime_type,
                    )
                )
        contents = types.Content(role="user", parts=parts)
    response = client.models.generate_content(
        model=request.model,
        contents=contents,
        config=config,
    )
    return ProviderResponse(
        text=_text_from_response(response),
        parsed=getattr(response, "parsed", None),
        usage=_usage_from_response(response),
        finish_reason=_finish_reason_from_response(response),
    )


def _embed_sync(request: EmbeddingRequest) -> list[float]:
    client = genai.Client(api_key=request.api_key)
    response = client.models.embed_content(
        model=request.model,
        contents=request.text,
        config=types.EmbedContentConfig(outputDimensionality=request.output_dimension),
    )
    embeddings = response.embeddings or []
    if not embeddings or not embeddings[0].values:
        raise ProviderError(
            "Gemini embedding response was empty",
            failure_class="empty_embedding",
            retryable=False,
        )
    values = [float(value) for value in embeddings[0].values]
    if len(values) != request.output_dimension:
        raise ProviderError(
            "Gemini embedding dimension did not match the request",
            failure_class="embedding_dimension_mismatch",
            retryable=False,
        )
    return values


class GeminiAdapter:
    capabilities = ProviderCapabilities(
        text=True,
        structured_json=True,
        image_input=True,
        embedding=True,
    )

    async def generate_text(self, request: ProviderRequest) -> ProviderResponse:
        return await asyncio.to_thread(_generate_content_sync, request)

    async def generate_json(self, request: ProviderRequest) -> ProviderResponse:
        return await asyncio.to_thread(_generate_content_sync, request)

    async def embed(self, request: EmbeddingRequest) -> list[float]:
        return await asyncio.to_thread(_embed_sync, request)

    def embed_sync(self, request: EmbeddingRequest) -> list[float]:
        return _embed_sync(request)

    def normalize_error(
        self, exc: BaseException, *, api_key: str | None = None
    ) -> ProviderError:
        message = redact_exact_secret_text(str(exc), api_key)
        code = getattr(exc, "code", None)
        status = getattr(exc, "status", None)
        retryable = code in {429, 500, 502, 503, 504} or status in {
            "RESOURCE_EXHAUSTED",
            "UNAVAILABLE",
        }
        return ProviderError(
            message[:1000],
            failure_class=type(exc).__name__,
            provider_status=str(status) if status is not None else None,
            provider_code=code,
            retryable=retryable,
        )
