import re
from collections.abc import Mapping, Sequence
from typing import Any


GEMINI_API_KEY_RE = re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b")
OPENAI_API_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")
JSON_API_KEY_RE = re.compile(r'("api_key"\s*:\s*")([^"]+)(")', re.IGNORECASE)
JSON_SECRET_KEY_RE = re.compile(
    r'("key"\s*:\s*")((?:AIza|sk-)[^"]+)(")', re.IGNORECASE
)

SENSITIVE_FIELD_NAMES = {
    "api_key",
    "apikey",
    "apiKey",
    "authorization",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "password",
}


def redact_secret_text(value: str) -> str:
    redacted = GEMINI_API_KEY_RE.sub("[REDACTED_GEMINI_API_KEY]", value)
    redacted = OPENAI_API_KEY_RE.sub("[REDACTED_OPENAI_API_KEY]", redacted)
    redacted = JSON_API_KEY_RE.sub(r'\1[REDACTED]\3', redacted)
    redacted = JSON_SECRET_KEY_RE.sub(r'\1[REDACTED]\3', redacted)
    return redacted


def redact_exact_secret_text(value: str, *secrets: str | None) -> str:
    redacted = redact_secret_text(value)
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def redact_exact_secrets(value: Any, *secrets: str | None) -> Any:
    if isinstance(value, str):
        return redact_exact_secret_text(value, *secrets)
    if isinstance(value, Mapping):
        return {
            key: redact_exact_secrets(item, *secrets) for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [redact_exact_secrets(item, *secrets) for item in value]
    return value


def redact_secrets(value: Any) -> Any:
    if isinstance(value, str):
        return redact_secret_text(value)
    if isinstance(value, Mapping):
        return {key: _redact_mapping_value(str(key), item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [redact_secrets(item) for item in value]
    return value


def _redact_mapping_value(key: str, value: Any) -> Any:
    normalized = key.replace("-", "_").lower()
    if normalized in SENSITIVE_FIELD_NAMES:
        return "[REDACTED]"
    if normalized == "key" and isinstance(value, str):
        redacted = redact_secret_text(value)
        return "[REDACTED]" if redacted != value else value
    return redact_secrets(value)
