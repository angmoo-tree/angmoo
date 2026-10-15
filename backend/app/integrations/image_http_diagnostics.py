"""Opt-in, bounded HTTP facts. Never retain remote messages or request content."""
import asyncio
import json
import re
from time import monotonic
import httpx
from app.domains.media.schemas import HttpDiagnostic, ProviderDiagnostic

ERROR_BYTES = 16 * 1024
ERROR_SECONDS = 1.0
_CODES = frozenset({"400", "401", "402", "403", "408", "413", "422", "429", "500", "502", "503", "504",
    "rate_limit_exceeded", "insufficient_quota", "invalid_api_key", "invalid_request_error"})
_CATEGORIES = ((httpx.ConnectTimeout, "connect_timeout"), (httpx.ReadTimeout, "read_timeout"),
    (httpx.WriteTimeout, "write_timeout"), (httpx.PoolTimeout, "pool_timeout"),
    (httpx.ConnectError, "connect_error"), (httpx.ReadError, "read_error"),
    (httpx.WriteError, "write_error"), (httpx.RemoteProtocolError, "remote_protocol_error"))


def transport_category(error):
    return next((name for cls, name in _CATEGORIES if isinstance(error, cls)), "other_transport")


async def error_fields(response, provider, secret):
    data = bytearray()
    state = "complete"
    try:
        async with asyncio.timeout(ERROR_SECONDS):
            async for chunk in response.aiter_bytes():
                room = ERROR_BYTES - len(data)
                data.extend(chunk[:room])
                if len(chunk) > room:
                    state = "truncated"
                    break
    except TimeoutError:
        state = "time_budget"
    except (httpx.TransportError, httpx.DecodingError):
        state = "body_read_failed"
    # Cancellation deliberately propagates. HTTP status remains the primary error.
    fields = {}
    if state == "complete":
        if not data:
            state = "no_body"
        else:
            try:
                value = json.loads(data)
                error = value.get("error") if isinstance(value, dict) else None
                code = error.get("code", error.get("type")) if isinstance(error, dict) else None
                if isinstance(code, (str, int)) and not isinstance(code, bool):
                    fields["provider_code"] = str(code) if str(code) in _CODES else "unknown"
            except (ValueError, RecursionError, UnicodeError):
                state = "non_json"
    identifier = response.headers.get("x-request-id", "")
    pattern = r"gen-[0-9]{1,20}-[A-Za-z0-9]{8,64}" if provider == "openrouter" else r"[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}"
    if re.fullmatch(pattern, identifier) and (not secret or secret not in identifier):
        fields["request_id"] = identifier
    if secret and fields.get("provider_code") == secret:
        fields.pop("provider_code")
    if state == "complete" and not fields:
        state = "no_safe_fields"
    return {**fields, "completeness": state}


def diagnostic(provider, *, category, phase, started, timeout, headers_ms=None, status=None, purpose="generation", **fields):
    limits = httpx.Timeout(timeout)
    value = HttpDiagnostic(purpose=purpose, category=category, observed_phase=phase,
        elapsed_ms=max(0, round((monotonic() - started) * 1000, 2)), headers_ms=headers_ms,
        status=status, connect_timeout_s=limits.connect, read_timeout_s=limits.read,
        write_timeout_s=limits.write, pool_timeout_s=limits.pool,
        **{"completeness": "no_body", **fields})
    return ProviderDiagnostic(kind="error", stage="submission", messages=[], provider=provider,
        truncated=value.completeness == "truncated", transport=value).model_dump(exclude_none=True)
