"""Image-key writes and reads under the original owner/purpose envelope."""
from uuid import uuid4
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.core import security
from app.domains.identity.contracts import CredentialPurpose
from app.domains.identity.models_media import MediaCredential
from app.domains.identity.service.credential_resolution import CredentialResolver
from app.domains.identity.exceptions import CredentialResolutionError


def find_credential(db: Session, *, owner_id: str, character_id: str, provider: str, purpose: CredentialPurpose) -> MediaCredential | None:
    return db.scalar(select(MediaCredential).where(MediaCredential.owner_id == owner_id,
        MediaCredential.character_scope == character_id, MediaCredential.provider == provider,
        MediaCredential.purpose == purpose.value))


def save_credential(db: Session, *, owner_id: str, character_id: str, provider: str,
                    purpose: CredentialPurpose, secret: str | None, expected_revision: int | None = None) -> MediaCredential:
    if purpose not in (CredentialPurpose.USER_IMAGE, CredentialPurpose.COMFY_PARTNER_IMAGE, CredentialPurpose.IMAGE_INTERPRETATION):
        raise CredentialResolutionError("media_credential_purpose_invalid")
    if purpose == CredentialPurpose.IMAGE_INTERPRETATION and (character_id or provider != "gemini"):
        raise CredentialResolutionError("interpretation_credential_scope_invalid")
    if purpose == CredentialPurpose.COMFY_PARTNER_IMAGE and (not character_id or provider != "comfyui"):
        raise CredentialResolutionError("comfy_partner_credential_scope_invalid")
    if purpose == CredentialPurpose.USER_IMAGE and (not character_id or provider not in {"novelai", "comfyui", "nanogpt", "openrouter"}):
        raise CredentialResolutionError("generation_credential_scope_invalid")
    row = find_credential(db, owner_id=owner_id, character_id=character_id, provider=provider, purpose=purpose)
    if row is None:
        if expected_revision not in (None, 0):
            raise CredentialResolutionError("media_credential_revision_conflict")
        row = MediaCredential(id=uuid4().hex, owner_id=owner_id, character_scope=character_id, provider=provider, purpose=purpose.value, revision=1)
        db.add(row)
    else:
        if expected_revision is not None and expected_revision != row.revision:
            raise CredentialResolutionError("media_credential_revision_conflict")
        previous = row.revision
        changed = db.execute(update(MediaCredential).where(MediaCredential.id == row.id,
            MediaCredential.revision == previous).values(revision=previous + 1))
        if changed.rowcount != 1:
            raise CredentialResolutionError("media_credential_revision_conflict")
        db.refresh(row)
    raw = (secret or "").strip()
    if len(raw) > 4096:
        raise CredentialResolutionError("media_credential_too_long")
    row.encrypted_secret = security.encrypt_secret(raw, scope=security.SecretScope(
        owner_id=owner_id, character_id=character_id, provider=provider, purpose=purpose.value)) if raw else None
    row.fingerprint = security.fingerprint_secret(raw) if raw else None
    row.enabled = bool(raw)
    db.flush()
    return row


def resolve_credential(row: MediaCredential | None, *, owner_id: str, character_id: str,
                       provider: str, purpose: CredentialPurpose, revision: int | None = None):
    if row is None or not row.enabled or (row.owner_id, row.character_scope, row.provider, row.purpose) != (owner_id, character_id, provider, purpose.value):
        raise CredentialResolutionError("media_credential_scope_or_key_invalid")
    if revision is not None and row.revision != revision:
        raise CredentialResolutionError("media_credential_revision_changed")
    return CredentialResolver.resolve_encrypted_material(encrypted_secret=row.encrypted_secret,
        credential_id=row.id, provider=provider, model="", fingerprint=row.fingerprint,
        purpose=purpose, owner_id=owner_id, character_id=character_id, stored_purpose=purpose.value)
