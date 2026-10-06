"""Authenticate original envelopes for an unpublished migration generation."""
from app.core import security


def authenticate_original_secret(envelope, scope):
    raw = security.decrypt_secret(envelope, scope=security.SecretScope(**scope))
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("migration_secret_empty")
    # Never return plaintext to the migration or keep it in a manifest.


class MigrationSecretInterpreter:
    def __call__(self, envelope, scope):
        authenticate_original_secret(envelope, scope)

    def rebind_image_pair(self, primary, primary_scope, partner, partner_scope, target_scope):
        import json
        raw = security.decrypt_secret(primary, scope=security.SecretScope(**primary_scope)) if primary else ""
        other = security.decrypt_secret(partner, scope=security.SecretScope(**partner_scope))
        if not isinstance(raw, str) or not isinstance(other, str) or not other.strip():
            raise ValueError("migration_secret_empty")
        return security.encrypt_secret(json.dumps({"version": "comfy-secrets.v1", "key": raw, "partner": other}),
            scope=security.SecretScope(**target_scope))
