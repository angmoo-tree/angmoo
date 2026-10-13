"""Shared current-row projection and immutable revision primitives.

Same Identity-owned Session/flush semantics; commands retain mutation ordering.
"""
import json
from sqlalchemy import select
from app.core import security
from app.domains.identity.exceptions import CredentialResolutionError
from app.domains.identity.models_world_credentials import WorldCredential, WorldCredentialRevision
from app.domains.identity.schemas import WorldCredentialPurpose, WorldCredentialRead

def find(db, *, owner_id, world_id, world_character_id, purpose):
    return db.scalar(select(WorldCredential).where(WorldCredential.owner_id == owner_id,
        WorldCredential.world_id == world_id, WorldCredential.world_character_id == world_character_id,
        WorldCredential.purpose == WorldCredentialPurpose(purpose).value).execution_options(populate_existing=True))



def metadata(row, *, purpose):
    if row is None:
        provider, model, thinking = ("novelai", "nai-diffusion-4-5-full", None) if purpose == "image" else (
            "google", "gemini-embedding-2" if purpose == "embedding" else "gemini-3.1-flash-lite",
            None if purpose == "embedding" else "medium" if purpose == "vision" else "high")
        return WorldCredentialRead(purpose=purpose, provider=provider, model=model, thinking_level=thinking,
            has_key=False, fingerprint=None, revision=0)
    primary, partner = bool(row.encrypted_secret), False
    if purpose == "image" and row.provider == "comfyui" and row.encrypted_secret:
        values = _comfy_secrets(security.decrypt_secret(row.encrypted_secret, scope=security.SecretScope(
            owner_id=row.owner_id, character_id=row.aad_character_id, provider=row.provider, purpose=row.aad_purpose)))
        primary, partner = bool(values.get("key")), bool(values.get("partner"))
    return WorldCredentialRead(purpose=purpose, provider=row.provider, model=row.model,
        thinking_level=row.thinking_level, has_key=primary, has_partner_key=partner, fingerprint=row.fingerprint, revision=row.revision)



def _preserve_revision(db, row):
    if db.get(WorldCredentialRevision, (row.id, row.revision)) is None:
        db.add(WorldCredentialRevision(credential_id=row.id, revision=row.revision,
            **{name: getattr(row, name) for name in ("provider", "model", "thinking_level", "encrypted_secret",
                "fingerprint", "aad_character_id", "aad_purpose")}))
        db.flush()



def _comfy_secrets(raw):
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        raise CredentialResolutionError("comfy_server_key_retired") from None
    if not isinstance(value, dict) or value.get("version") != "comfy-secrets.v1" or not all(isinstance(value.get(k), str) for k in ("key", "partner")):
        raise CredentialResolutionError("world_credential_secret_invalid")
    if value["key"]:
        raise CredentialResolutionError("comfy_server_key_retired")
    return value
