"""Scope-bound image provider keys and explicit, revision-safe revocation."""
from uuid import uuid4
import json
from sqlalchemy import select, update
from app.core import security
from app.domains.identity.contracts import CredentialPurpose
from app.domains.identity.exceptions import CredentialResolutionError
from app.domains.identity.models_world_credentials import WorldCredential, WorldCredentialRevision
from app.domains.identity.models_world_image_credentials import WorldImageProviderCredential as Vault
from app.domains.identity.schemas import WorldImageProviderKeyRead


def key_purpose(provider):
    if provider == "comfyui":
        return CredentialPurpose.COMFY_PARTNER_IMAGE.value
    if provider in {"novelai", "nanogpt", "openrouter"}:
        return CredentialPurpose.USER_IMAGE.value
    raise CredentialResolutionError("world_credential_profile_invalid")


def find(db, *, owner_id, world_id, world_character_id, provider):
    return db.scalar(select(Vault).where(Vault.owner_id == owner_id, Vault.world_id == world_id,
        Vault.world_character_id == world_character_id, Vault.provider == provider,
        Vault.purpose == key_purpose(provider)).execution_options(populate_existing=True))


def metadata(db, *, owner_id, world_id, world_character_id, provider):
    row = find(db, owner_id=owner_id, world_id=world_id, world_character_id=world_character_id, provider=provider)
    active = bool(row and row.enabled and not row.tombstone and row.encrypted_secret)
    return WorldImageProviderKeyRead(provider=provider, purpose=key_purpose(provider), has_key=active,
        fingerprint=row.fingerprint if active else None, key_revision=row.revision if row else 0)


def _secret(row):
    if not row or not row.enabled or row.tombstone or not row.encrypted_secret:
        return ""
    return security.decrypt_secret(row.encrypted_secret, scope=security.SecretScope(owner_id=row.owner_id,
        character_id=row.aad_character_id, provider=row.provider, purpose=row.aad_purpose))


def _write(db, *, owner_id, world_id, world_character_id, provider, raw, expected_revision, tombstone=False):
    row = find(db, owner_id=owner_id, world_id=world_id, world_character_id=world_character_id, provider=provider)
    if expected_revision != (row.revision if row else 0):
        raise CredentialResolutionError("world_image_key_revision_conflict")
    if len(raw) > 4096:
        raise CredentialResolutionError("world_credential_too_long")
    if row is None:
        row = Vault(id=uuid4().hex, owner_id=owner_id, world_id=world_id, world_character_id=world_character_id,
            provider=provider, purpose=key_purpose(provider), revision=1,
            aad_character_id=world_character_id, aad_purpose=key_purpose(provider))
        db.add(row)
    else:
        changed = db.execute(update(Vault).where(Vault.id == row.id, Vault.revision == expected_revision)
            .values(revision=expected_revision + 1))
        if changed.rowcount != 1:
            raise CredentialResolutionError("world_image_key_revision_conflict")
        db.refresh(row)
    row.encrypted_secret = security.encrypt_secret(raw, scope=security.SecretScope(owner_id=owner_id,
        character_id=row.aad_character_id, provider=provider, purpose=row.aad_purpose)) if raw else None
    row.fingerprint = security.fingerprint_secret(raw) if raw else None
    row.enabled, row.tombstone = bool(raw), tombstone
    db.flush()
    return row


def select_provider(db, *, owner_id, world_id, world_character_id, data):
    from .world_credentials import find as current, _preserve_revision, metadata as selected_metadata
    scope = dict(owner_id=owner_id, world_id=world_id, world_character_id=world_character_id)
    row = current(db, **scope, purpose="image")
    if data.expected_revision != (row.revision if row else 0):
        raise CredentialResolutionError("world_credential_revision_conflict")
    vault = find(db, **scope, provider=data.provider)
    if data.expected_key_revision != (vault.revision if vault else 0):
        raise CredentialResolutionError("world_image_key_revision_conflict")
    raw = data.api_key.get_secret_value().strip() if data.api_key else ""
    if data.provider == "comfyui" and raw:
        raise CredentialResolutionError("comfy_server_key_not_supported")
    supplied = data.partner_api_key if data.provider == "comfyui" else data.api_key
    if supplied is not None or data.clear_partner_key:
        raw = "" if data.clear_partner_key else supplied.get_secret_value().strip()
        vault = _write(db, **scope, provider=data.provider, raw=raw,
            expected_revision=data.expected_key_revision, tombstone=data.clear_partner_key)
        if data.clear_partner_key:
            _revoke_snapshots(db, row, data.provider)
    else:
        raw = _secret(vault)
    if row is None:
        row = WorldCredential(id=uuid4().hex, **scope, purpose="image", provider=data.provider,
            model=data.model, revision=1, aad_character_id=world_character_id, aad_purpose="user_image")
        db.add(row)
    else:
        _preserve_revision(db, row)
        changed = db.execute(update(WorldCredential).where(WorldCredential.id == row.id,
            WorldCredential.revision == data.expected_revision).values(revision=data.expected_revision + 1))
        if changed.rowcount != 1:
            raise CredentialResolutionError("world_credential_revision_conflict")
        db.refresh(row)
    row.provider, row.model, row.thinking_level = data.provider, data.model, None
    row.aad_character_id, row.aad_purpose = world_character_id, "user_image"
    executable = json.dumps({"version": "comfy-secrets.v1", "key": "", "partner": raw}) if data.provider == "comfyui" and raw else raw
    row.encrypted_secret = security.encrypt_secret(executable, scope=security.SecretScope(owner_id=owner_id,
        character_id=world_character_id, provider=data.provider, purpose="user_image")) if executable else None
    row.fingerprint = security.fingerprint_secret(raw) if raw else None
    db.flush()
    _preserve_revision(db, row)
    return selected_metadata(row, purpose="image").model_copy(update={"key_revision": vault.revision if vault else 0})


def _revoke_snapshots(db, current, provider):
    if current is None:
        return
    # A purpose/provider delete revokes every execution copy of that key,
    # including work admitted before rotation. Other providers stay valid.
    db.execute(update(WorldCredentialRevision).where(WorldCredentialRevision.credential_id == current.id,
        WorldCredentialRevision.provider == provider).values(encrypted_secret=None, fingerprint=None))
    if current.provider == provider:
        current.encrypted_secret, current.fingerprint = None, None
        db.flush()


def delete_provider(db, *, owner_id, world_id, world_character_id, data):
    from .world_credentials import find as selected, metadata as selected_metadata, _preserve_revision
    scope = dict(owner_id=owner_id, world_id=world_id, world_character_id=world_character_id)
    current = selected(db, **scope, purpose="image")
    if current is None or current.revision != data.expected_revision:
        raise CredentialResolutionError("world_credential_revision_conflict")
    provider = data.provider or current.provider
    key = find(db, **scope, provider=provider)
    expected = data.expected_key_revision
    if expected != (key.revision if key else 0):
        raise CredentialResolutionError("world_image_key_revision_conflict")
    key = _write(db, **scope, provider=provider, raw="", expected_revision=expected, tombstone=True)
    _revoke_snapshots(db, current, provider)
    if current.provider == provider:
        changed = db.execute(update(WorldCredential).where(WorldCredential.id == current.id,
            WorldCredential.revision == data.expected_revision).values(revision=data.expected_revision + 1))
        if changed.rowcount != 1:
            raise CredentialResolutionError("world_credential_revision_conflict")
        db.refresh(current)
        _preserve_revision(db, current)
    return selected_metadata(current, purpose="image").model_copy(update={"key_revision": key.revision})
