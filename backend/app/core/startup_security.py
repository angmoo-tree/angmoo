from __future__ import annotations

import secrets
from collections.abc import Callable
from urllib.parse import urlsplit

from app.core import security
from app.core.config import DEFAULT_APP_SECRET, Settings, settings


KmsRoundTrip = Callable[[str], str]


class StartupSecurityError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _default_kms_round_trip(plaintext: str) -> str:
    envelope = security.encrypt_secret(plaintext)
    return security.decrypt_secret(envelope)


def _valid_kms_endpoint(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    )


def validate_startup_security(
    config: Settings = settings,
    *,
    kms_round_trip: KmsRoundTrip | None = None,
) -> None:
    if config.app_env != "production":
        return

    if not config.app_secret.strip() or config.app_secret == DEFAULT_APP_SECRET:
        raise StartupSecurityError("unsafe_app_secret")

    if config.credential_encryption_provider not in {"oci_kms", "oci-kms"}:
        raise StartupSecurityError("unsafe_credential_provider")

    if not (
        config.oci_kms_key_id
        and config.oci_kms_crypto_endpoint
        and config.oci_region
    ):
        raise StartupSecurityError("missing_kms_config")

    if not _valid_kms_endpoint(config.oci_kms_crypto_endpoint):
        raise StartupSecurityError("invalid_kms_endpoint")

    if config.oci_auth_mode != "instance_principal":
        raise StartupSecurityError("invalid_oci_auth_mode")

    plaintext = secrets.token_urlsafe(32)
    probe = kms_round_trip or _default_kms_round_trip
    try:
        recovered = probe(plaintext)
    except Exception as exc:
        raise StartupSecurityError("kms_preflight_failed") from exc
    if recovered != plaintext:
        raise StartupSecurityError("kms_preflight_failed")
