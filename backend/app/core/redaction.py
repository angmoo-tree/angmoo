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
    "app_secret",
    "session_token",
    "encrypted_api_key",
    "encrypted_pollinations_api_key",
    "encrypted_replicate_api_key",
    "credential_payload",
    "full_prompt",
    "provider_response",
}

SUPPORT_BUNDLE_DEFAULT_EXCLUDED_FIELDS = frozenset(
    {
        *SENSITIVE_FIELD_NAMES,
        "authorization_header",
        "cookie_header",
        "private_chat",
        "private_chat_messages",
        "sns_content",
        "media_original",
        "postgresql_dump",
        "raw_prompt",
        "raw_provider_response",
    }
)


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


def sanitize_support_bundle_metadata(value: Any) -> Any:
    """Return support-safe metadata while excluding private payload fields.

    Support bundles are intentionally metadata-first. Exact secrets are redacted
    recursively and fields that can contain private content are omitted instead
    of being copied into a diagnostic archive.
    """

    if isinstance(value, Mapping):
        sanitized: dict[Any, Any] = {}
        for key, item in value.items():
            normalized = str(key).replace("-", "_").lower()
            if normalized in SUPPORT_BUNDLE_DEFAULT_EXCLUDED_FIELDS:
                continue
            sanitized[key] = sanitize_support_bundle_metadata(item)
        return sanitized
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [sanitize_support_bundle_metadata(item) for item in value]
    return redact_secrets(value)


def _redact_mapping_value(key: str, value: Any) -> Any:
    normalized = key.replace("-", "_").lower()
    if normalized in SENSITIVE_FIELD_NAMES:
        return "[REDACTED]"
    if normalized == "key" and isinstance(value, str):
        redacted = redact_secret_text(value)
        return "[REDACTED]" if redacted != value else value
    return redact_secrets(value)
