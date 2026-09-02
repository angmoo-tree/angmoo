from __future__ import annotations

import asyncio
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.core.redaction import redact_exact_secret_text
from app.providers.contracts import (
    EmbeddingRequest,
    ProviderCapabilities,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
)


_GEMINI_DEVELOPER_SCHEMA_KEYS = frozenset(
    {
        "type",
        "properties",
        "required",
        "items",
        "enum",
        "format",
        "description",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "nullable",
        "pattern",
    }
)


def build_gemini_developer_response_schema(
    model: type[BaseModel],
) -> dict[str, Any]:
    """Convert a strict Pydantic model to Gemini Developer API JSON Schema.

    The transport schema only contains the subset accepted by Gemini and has
    all local references inlined.  Callers must still validate the returned
    payload with the original strict Pydantic model before applying it.
    """

    source = model.model_json_schema()
    definitions = source.get("$defs", {})

    def convert(value: Any) -> Any:
        if isinstance(value, list):
            return [convert(item) for item in value]
        if not isinstance(value, dict):
            return value

        if "$ref" in value:
            reference = value["$ref"]
            prefix = "#/$defs/"
            if not isinstance(reference, str) or not reference.startswith(prefix):
                raise ValueError(f"unsupported response schema reference: {reference}")
            name = reference[len(prefix) :]
            target = definitions.get(name)
            if not isinstance(target, dict):
                raise ValueError(f"missing response schema definition: {name}")
            merged = dict(target)
            merged.update({key: item for key, item in value.items() if key != "$ref"})
            return convert(merged)

        variants = value.get("anyOf")
        if isinstance(variants, list):
            non_null = [
                item
                for item in variants
                if not (isinstance(item, dict) and item.get("type") == "null")
            ]
            has_null = len(non_null) != len(variants)
            if has_null and len(non_null) == 1:
                converted = convert(non_null[0])
                if not isinstance(converted, dict):
                    raise ValueError("nullable response schema must resolve to an object")
                converted_type = converted.get("type")
                if isinstance(converted_type, str):
                    converted["type"] = [converted_type, "null"]
                else:
                    raise ValueError(
                        "nullable response schema must have one concrete type"
                    )
                return converted
            raise ValueError("unsupported response schema union")

        converted: dict[str, Any] = {}
        for key, item in value.items():
            if key == "properties" and isinstance(item, dict):
                converted[key] = {
                    property_name: convert(property_schema)
                    for property_name, property_schema in item.items()
                }
            elif key in _GEMINI_DEVELOPER_SCHEMA_KEYS:
                converted[key] = convert(item)
        return converted

    converted = convert(source)
    if not isinstance(converted, dict):
        raise ValueError("response schema root must be an object")
    return converted


def build_generate_content_config(
    *,
    model: str,
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
    }
    if isinstance(response_schema, dict):
        # Developer API accepts ordinary JSON Schema through this field.  The
        # older OpenAPI-style responseSchema path has a smaller, product-
        # specific subset and can reject otherwise valid nested schemas.
        config_kwargs["responseJsonSchema"] = response_schema
    elif response_schema is not None:
        config_kwargs["responseSchema"] = response_schema
    thinking_config = resolve_gemini_thinking_config(
        model=model,
        thinking_level=thinking_level,
    )
    if thinking_config is not None:
        config_kwargs["thinkingConfig"] = thinking_config
    return types.GenerateContentConfig(**config_kwargs)


def resolve_gemini_thinking_config(
    *,
    model: str,
    thinking_level: str | None,
) -> types.ThinkingConfig | None:
    """Map Angmoo's bounded intent to the selected model family's API.

    Gemini 3 supports ``thinkingLevel`` while Gemini 2.5 uses a numeric
    ``thinkingBudget``.  Gemma models do not accept Gemini thinking controls.
    Unknown families fail before provider I/O instead of guessing a config.
    """

    normalized_model = model.strip().lower()
    normalized_level = (
        None if thinking_level is None else thinking_level.strip().lower()
    )
    if normalized_model.startswith("gemma-"):
        return None
    if normalized_model.startswith("gemini-3."):
        if not normalized_level:
            return None
        return types.ThinkingConfig(thinkingLevel=normalized_level)
    if normalized_model.startswith("gemini-2.5-"):
        if not normalized_level:
            return None
        if normalized_level != "low":
            raise ValueError(
                "gemini_2_5_thinking_level_requires_explicit_budget_policy"
            )
        return types.ThinkingConfig(thinkingBudget=0)
    raise ValueError(f"unsupported_gemini_thinking_model_family:{model}")


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
        model=request.model,
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
