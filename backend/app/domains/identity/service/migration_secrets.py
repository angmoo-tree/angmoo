"""Authenticate original envelopes for an unpublished migration generation."""
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar

from pydantic import SecretStr

from app.core import security

_migration_secret_source = ContextVar("migration_secret_source", default=None)


@contextmanager
def migration_secret_source(source: Callable[[], str]):
    """Composition-root binding for immutable historical Alembic revisions."""
    token = _migration_secret_source.set(source)
    try:
        yield
    finally:
        _migration_secret_source.reset(token)


def authenticate_original_secret(envelope, scope, *, app_secret: str):
    raw = security.decrypt_local_secret(
        envelope, scope=security.SecretScope(**scope), app_secret=app_secret,
    )
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("migration_secret_empty")
    # Never return plaintext to the migration or keep it in a manifest.


class MigrationSecretInterpreter:
    def __init__(self, *, secret_source: Callable[[], str] | None = None) -> None:
        self._secret_source = secret_source or _migration_secret_source.get()
        self._app_secret: SecretStr | None = None

    def _secret(self) -> str:
        # Empty/older transitions need no credential material. Once needed,
        # use one owned-root value throughout authentication and rebinding.
        if self._app_secret is None:
            if self._secret_source is None:
                raise ValueError("migration_secret_source_required")
            app_secret = self._secret_source()
            if not isinstance(app_secret, str) or not app_secret.strip():
                raise ValueError("migration_app_secret_empty")
            self._app_secret = SecretStr(app_secret)
        return self._app_secret.get_secret_value()

    def __call__(self, envelope, scope):
        authenticate_original_secret(envelope, scope, app_secret=self._secret())

    def rebind_image_pair(self, primary, primary_scope, partner, partner_scope, target_scope):
        import json
        app_secret = self._secret()
        raw = security.decrypt_local_secret(primary, scope=security.SecretScope(**primary_scope), app_secret=app_secret) if primary else ""
        other = security.decrypt_local_secret(partner, scope=security.SecretScope(**partner_scope), app_secret=app_secret)
        if not isinstance(raw, str) or not isinstance(other, str) or not other.strip():
            raise ValueError("migration_secret_empty")
        return security.encrypt_local_secret(json.dumps({"version": "comfy-secrets.v1", "key": raw, "partner": other}),
            scope=security.SecretScope(**target_scope), app_secret=app_secret)
