from __future__ import annotations

from app.domains.identity.exceptions import BrowserSessionConfigurationError
from app.domains.identity.browser_session import validate_browser_session_settings
from app.config import DEFAULT_APP_SECRET, Settings, settings


class StartupSecurityError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def validate_startup_security(config: Settings = settings) -> None:
    try:
        validate_browser_session_settings(config)
    except BrowserSessionConfigurationError as exc:
        raise StartupSecurityError(exc.args[0]) from exc
    # Official embedded/contributor/test profiles provide their own local settings.
    # Removing hosted KMS must not turn the retired production profile into an
    # unchecked server startup.
    if config.app_env == "production":
        raise StartupSecurityError("unsupported_runtime_profile")
    if config.credential_encryption_provider not in {"local", "dev", "local-v2"}:
        raise StartupSecurityError("unsafe_credential_provider")
    if config.app_env == "local":
        if not config.app_secret.strip() or config.app_secret == DEFAULT_APP_SECRET:
            raise StartupSecurityError("unsafe_app_secret")
        if config.credential_encryption_provider != "local":
            raise StartupSecurityError("unsafe_credential_provider")
        from urllib.parse import urlsplit
        uri=urlsplit(config.database_url)
        local_postgresql=(uri.scheme=='postgresql+psycopg' and uri.hostname in {'127.0.0.1','::1'}
            and bool(uri.username) and bool(uri.password) and bool(uri.path.strip('/')))
        if not config.database_url.startswith("sqlite+pysqlite:///") and not local_postgresql:
            raise StartupSecurityError("local_database_required")
        launch_token = config.desktop_launch_token
        if launch_token is None or len(launch_token) < 32:
            raise StartupSecurityError("local_desktop_token_required")
        if config.desktop_allowed_origin != "http://tauri.localhost":
            raise StartupSecurityError("local_desktop_origin_invalid")
        if config.api_docs_enabled:
            raise StartupSecurityError("local_api_docs_forbidden")
        if config.signup_enabled:
            raise StartupSecurityError("local_signup_forbidden")
