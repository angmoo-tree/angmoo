"""Azure translation transport and its existing provider character budget.

This client returns None for disabled/unavailable/failed translation. Character
prompt caching and the decision to request translation stay in the caller.
"""
from datetime import UTC, datetime
import json
from typing import Any
from urllib.error import URLError
from urllib.error import HTTPError
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


def _translate_ko_to_en_with_azure(text: str, *, period=None) -> str | None:
    if settings.translation_provider != "azure":
        return None
    api_key = settings.azure_translator_key
    if not api_key:
        return None
    char_count = len(text)
    reservation = _reserve_translation_chars(char_count, period=period)
    if reservation is None:
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
        if not isinstance(translated, str) or not translated.strip():
            raise ValueError("translation_response_invalid")
        _settle_translation_chars(reservation, "consumed")
        return translated.strip()
    except HTTPError as exc:
        if 400 <= exc.code < 500:
            _release_translation_chars(reservation)
        else:
            _settle_translation_chars(reservation, "unknown")
        return None
    except Exception:
        # A response or a transport failure may already have been billed.
        # Unknown outcomes retain their original reservation, never a refund.
        _settle_translation_chars(reservation, "unknown")
        return None


def _default_period():
    from app.contracts.environment import AccountingPeriod
    from app.core.calendar import local_period
    now = datetime.now(UTC)
    bounds = local_period(now, "UTC", "month")
    return AccountingPeriod(now.strftime("%Y-%m"), "UTC", (bounds,), bounds[1], natural_bounds=bounds)


def _translation_ledger(path):
    from app.core.calendar import local_period
    from app.core.calendar_ledger import add_bucket, validated_ledger, CalendarLedgerInvalid
    if not path.exists():
        if path.with_suffix(path.suffix + ".initialized").exists():
            raise CalendarLedgerInvalid("translation_quota_recovery_required")
        return {"version": 2, "ledger": {"version": 1, "buckets": {}}, "reservations": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("version") == 2:
            validated_ledger(value["ledger"])
            if not isinstance(value["reservations"], dict):
                raise ValueError()
            for entry in value["reservations"].values():
                if (not isinstance(entry, dict) or entry.get("bucket") not in value["ledger"]["buckets"]
                    or type(entry.get("count")) is not int or entry["count"] < 0
                    or entry.get("status") not in {"reserved", "consumed", "unknown", "released"}):
                    raise ValueError()
            return value
        month, count = value["month"], value["chars"]
        if type(count) is not int or count < 0:
            raise ValueError()
        instant = datetime.strptime(month, "%Y-%m").replace(tzinfo=UTC)
        ledger = add_bucket({"version": 1, "buckets": {}}, "legacy:utc:" + month,
                            local_period(instant, "UTC", "month"), count)
        return {"version": 2, "ledger": ledger, "reservations": {}}
    except (OSError, ValueError, TypeError, KeyError):
        raise CalendarLedgerInvalid("translation_quota_recovery_required") from None


def _reserve_translation_chars(char_count: int, *, period=None) -> str | None:
    from app.core.atomic_json import locked_json, write_json
    from app.core.calendar_ledger import add_bucket, ledger_usage, CalendarLedgerInvalid
    from app.core.calendar import local_period
    from app.core.ids import uuid7_string
    if type(char_count) is not int or char_count < 0:
        return None
    limit = settings.translation_monthly_char_limit
    if limit <= 0:
        return "unlimited"
    period = period or _default_period()
    path = settings.media_root_path / "translation-usage.json"
    try:
        with locked_json(path):
            usage = _translation_ledger(path)
            if ledger_usage(usage["ledger"], period) + char_count > limit:
                return None
            identifier = uuid7_string()
            key = "month:" + period.timezone + ":" + period.key
            from app.core.calendar import wall_time
            first_day = datetime.strptime(period.key, "%Y-%m").date()
            bounds = period.natural_bounds or local_period(wall_time(first_day, 0, 0, period.timezone), period.timezone, "month")
            usage["ledger"] = add_bucket(usage["ledger"], key, bounds, char_count)
            usage["reservations"][identifier] = {"bucket": key, "count": char_count, "status": "reserved"}
            usage.update(month=period.key, chars=ledger_usage(usage["ledger"], period))
            path.with_suffix(path.suffix + ".initialized").touch(exist_ok=True)
            write_json(path, usage)
            return identifier
    except (OSError, CalendarLedgerInvalid):
        return None  # An unavailable ledger cannot authorize extra billing.


def _release_translation_chars(reservation: str) -> None:
    from app.core.atomic_json import locked_json, write_json
    from app.core.calendar_ledger import CalendarLedgerInvalid
    if reservation == "unlimited":
        return
    path = settings.media_root_path / "translation-usage.json"
    try:
        with locked_json(path):
            usage = _translation_ledger(path)
            entry = usage["reservations"].get(reservation)
            if not entry or entry["status"] != "reserved":
                return
            bucket = usage["ledger"]["buckets"][entry["bucket"]]
            bucket["count"] = max(0, bucket["count"] - entry["count"])
            entry["status"] = "released"
            if entry["bucket"] == "month:UTC:" + usage.get("month", "") or entry["bucket"].endswith(":" + usage.get("month", "")):
                usage["chars"] = max(0, usage.get("chars", 0) - entry["count"])
            write_json(path, usage)
    except (OSError, CalendarLedgerInvalid):
        return  # Keep the conservative charge if durable release is unavailable.


def _settle_translation_chars(reservation: str, status: str) -> None:
    from app.core.atomic_json import locked_json, write_json
    from app.core.calendar_ledger import CalendarLedgerInvalid
    if reservation == "unlimited":
        return
    path = settings.media_root_path / "translation-usage.json"
    try:
        with locked_json(path):
            usage = _translation_ledger(path)
            entry = usage["reservations"].get(reservation)
            if entry and entry["status"] == "reserved":
                entry["status"] = status
                write_json(path, usage)
    except (OSError, CalendarLedgerInvalid):
        return


def _read_translation_usage(path: Any, month: str) -> dict[str, Any]:
    return _translation_ledger(path)


def _write_translation_usage(path: Any, usage: dict[str, Any]) -> None:
    from app.core.atomic_json import write_json
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, usage)
