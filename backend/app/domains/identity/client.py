from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import settings
from app.integrations import bounded_http


TURNSTILE_SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TURNSTILE_MAX_TOKEN_LENGTH = 2048
TURNSTILE_MAX_RESPONSE_BYTES = 16 * 1024

logger = logging.getLogger(__name__)


from app.domains.identity.exceptions import (
    TurnstileError,
    TurnstileVerificationError,
    TurnstileConfigError,
    TurnstileUnavailableError,
)


def verify_turnstile_or_raise(token: str | None) -> None:
    if not settings.turnstile_enabled:
        return

    normalized_token = (token or "").strip()
    if not normalized_token or len(normalized_token) > TURNSTILE_MAX_TOKEN_LENGTH:
        logger.info("turnstile_verification_failed reason=missing_or_invalid_token")
        raise TurnstileVerificationError("Turnstile token is missing or invalid")

    secret = settings.turnstile_secret_key
    if secret is None:
        logger.error("turnstile_unavailable reason=missing_secret")
        raise TurnstileConfigError("Turnstile secret key is not configured")

    body = urlencode({"secret": secret, "response": normalized_token}).encode("utf-8")
    request = Request(
        TURNSTILE_SITEVERIFY_URL,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "Angmoo/1.0",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=settings.turnstile_timeout_seconds) as response:
            payload = json.loads(
                bounded_http.read_bounded_response(
                    response,
                    max_bytes=TURNSTILE_MAX_RESPONSE_BYTES,
                ).decode("utf-8")
            )
    except HTTPError as exc:
        logger.warning("turnstile_unavailable reason=http_error status=%s", exc.code)
        raise TurnstileUnavailableError("Turnstile verification failed") from exc
    except TimeoutError as exc:
        logger.warning("turnstile_unavailable reason=timeout")
        raise TurnstileUnavailableError("Turnstile verification timed out") from exc
    except URLError as exc:
        reason = getattr(exc, "reason", None)
        reason_label = "timeout" if isinstance(reason, TimeoutError) else "network_error"
        logger.warning("turnstile_unavailable reason=%s", reason_label)
        raise TurnstileUnavailableError("Turnstile verification failed") from exc
    except bounded_http.ResponseTooLargeError as exc:
        logger.warning("turnstile_unavailable reason=response_too_large")
        raise TurnstileUnavailableError("Turnstile verification failed") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("turnstile_unavailable reason=invalid_json")
        raise TurnstileUnavailableError("Turnstile verification returned invalid JSON") from exc

    if payload.get("success") is True:
        return

    error_codes = payload.get("error-codes")
    if isinstance(error_codes, list):
        safe_codes = ",".join(str(code) for code in error_codes[:5])
    else:
        safe_codes = "unknown"
    logger.info("turnstile_verification_failed reason=siteverify_rejected codes=%s", safe_codes)
    raise TurnstileVerificationError("Turnstile verification failed")
