"""Official Developer API full generateContentRequest counting (SDK opt-in seam).

The locked SDK excludes system/schema/config from Developer count_tokens. This
bounded adapter sends the same prepared SDK values via the documented HTTP API.
"""
from datetime import UTC, datetime
import asyncio
from hashlib import sha256
import json
import re

import httpx

from app.providers.gemini import prepare_generate_request
from app.providers.input_budget import InputBudgetError, ModelTokenProfile

REVISION = "gemini-models-countTokens.v1"
BASE = "https://generativelanguage.googleapis.com/v1beta/"
REQUEST_TIMEOUT_SECONDS = 10.0


class GeminiModelTokenCounter:
    def __init__(self, *, transport=None):
        self.transport = transport

    def model_id(self, value):
        model = value.removeprefix("models/")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", model):
            raise InputBudgetError("model_budget_unsupported")
        return model

    async def _request(self, request, *, operation, body=None):
        model = self.model_id(request.model)
        try:
            # httpx's read timeout restarts for each chunk. Also bound the full
            # lookup/count request so a slow successful stream cannot hold the
            # activity's admission indefinitely.
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS), httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False, transport=self.transport
            ) as client:
                async with client.stream("GET" if body is None else "POST", BASE + "models/" + model + (":countTokens" if body is not None else ""),
                    headers={"x-goog-api-key": request.api_key}, json=body) as response:
                    if response.status_code != 200:
                        raise InputBudgetError("activity_input_budget_unavailable")
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > 1024 * 1024:
                            raise InputBudgetError("activity_input_budget_unavailable")
                    return json.loads(data)
        except (httpx.HTTPError, ValueError, TimeoutError) as exc:
            if isinstance(exc, InputBudgetError):
                raise
            raise InputBudgetError("activity_input_budget_unavailable") from None

    async def profile(self, request):
        data = await self._request(request, operation="models_get")
        if not isinstance(data, dict) or data.get("name") != "models/" + self.model_id(request.model):
            raise InputBudgetError("model_budget_unsupported")
        methods = data.get("supportedGenerationMethods")
        if (not isinstance(methods, list)
                or any(not isinstance(method, str) or not method.strip() for method in methods)
                or "generateContent" not in methods):
            raise InputBudgetError("model_budget_unsupported")
        return ModelTokenProfile("google", request.model, data.get("version"), data.get("inputTokenLimit"),
            data.get("outputTokenLimit"), REVISION, "https://ai.google.dev/api/models", datetime.now(UTC).isoformat())

    async def count(self, request, profile):
        if request.model != profile.model or profile.revision != REVISION:
            raise InputBudgetError("model_budget_unsupported")
        body = prepare_generate_request(request).count_request(request.model)
        fingerprint = sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        data = await self._request(request, operation="count_tokens", body=body)
        tokens = data.get("totalTokens") if isinstance(data, dict) else None
        if type(tokens) is not int or tokens < 0:
            raise InputBudgetError("activity_input_budget_unavailable")
        return tokens, fingerprint
