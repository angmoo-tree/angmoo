"""Azure translation transport and its existing provider character budget.

This client returns None for disabled/unavailable/failed translation. Character
prompt caching and the decision to request translation stay in the caller.
"""
from datetime import UTC, datetime
import json
from threading import Lock
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request

from app.config import settings
from app.integrations import bounded_http, provider_http

PROVIDER_SENSITIVE_HEADERS = frozenset({
    "Authorization", "Ocp-Apim-Subscription-Key", "Ocp-Apim-Subscription-Region",
})

def _open_translation_request(request: Request, timeout_seconds: float):
    endpoint = urlparse(settings.azure_translator_endpoint)
    if not endpoint.hostname:
        raise URLError("Azure Translator endpoint was not allowed")
    translate_path = f"{endpoint.path.rstrip('/')}/translate"
    try:
        return provider_http.open_validated_request(
            request,
            timeout_seconds=timeout_seconds,
            initial_validator=lambda url: provider_http.validate_public_https_url(
                url,
                allowed_hosts={endpoint.hostname},
                allowed_path_prefixes={translate_path},
            ),
            redirect_validator=provider_http.validate_public_https_url,
            sensitive_headers=PROVIDER_SENSITIVE_HEADERS,
            allow_cross_origin_redirects=False,
        )
    except provider_http.ProviderUrlError as exc:
        raise URLError("Azure Translator URL was not allowed") from exc


def _translate_ko_to_en_with_azure(text: str) -> str | None:
    if settings.translation_provider != "azure":
        return None
    api_key = settings.azure_translator_key
    if not api_key:
        return None
    char_count = len(text)
    if not _reserve_translation_chars(char_count):
        return None

    try:
        query = urlencode({"api-version": "3.0", "from": "ko", "to": "en"})
        url = f"{settings.azure_translator_endpoint}/translate?{query}"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Ocp-Apim-Subscription-Key": api_key,
            "User-Agent": "Angmoo/1.0",
        }
        region = settings.azure_translator_region
        if region:
            headers["Ocp-Apim-Subscription-Region"] = region
        body = json.dumps([{"Text": text}], ensure_ascii=False).encode("utf-8")
        request = Request(url, data=body, headers=headers, method="POST")
        with _open_translation_request(
            request,
            settings.translation_timeout_seconds,
        ) as response:
            payload = json.loads(
                bounded_http.read_bounded_response(
                    response,
                    max_bytes=bounded_http.MAX_PROVIDER_JSON_BYTES,
                ).decode("utf-8")
            )
        translated = payload[0]["translations"][0]["text"]
        return translated.strip() if isinstance(translated, str) else None
    except Exception:
        _release_translation_chars(char_count)
        return None


def _reserve_translation_chars(char_count: int) -> bool:
    limit = settings.translation_monthly_char_limit
    if limit <= 0:
        return True
    usage_path = settings.media_root_path / "translation-usage.json"
    month = datetime.now(UTC).strftime("%Y-%m")
    with _TRANSLATION_USAGE_LOCK:
        usage = _read_translation_usage(usage_path, month)
        if usage["chars"] + char_count > limit:
            return False
        usage["chars"] += char_count
        _write_translation_usage(usage_path, usage)
    return True


def _release_translation_chars(char_count: int) -> None:
    limit = settings.translation_monthly_char_limit
    if limit <= 0:
        return
    usage_path = settings.media_root_path / "translation-usage.json"
    month = datetime.now(UTC).strftime("%Y-%m")
    with _TRANSLATION_USAGE_LOCK:
        usage = _read_translation_usage(usage_path, month)
        usage["chars"] = max(0, usage["chars"] - char_count)
        _write_translation_usage(usage_path, usage)


def _read_translation_usage(path: Any, month: str) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    if raw.get("month") != month or not isinstance(raw.get("chars"), int):
        return {"month": month, "chars": 0}
    return {"month": month, "chars": max(0, raw["chars"])}


def _write_translation_usage(path: Any, usage: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(usage, ensure_ascii=False), encoding="utf-8")


_TRANSLATION_USAGE_LOCK = Lock()
