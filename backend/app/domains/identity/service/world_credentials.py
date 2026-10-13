"""Purpose-bound direct key writes and resolver. Never consult a global picker."""
from uuid import uuid4
from dataclasses import replace

from sqlalchemy import delete as sql_delete, select, update

from app.core import security
from app.domains.identity.contracts import CredentialPurpose
from app.domains.identity.exceptions import CredentialResolutionError
from app.domains.identity.models_world_credentials import WorldCredential, WorldCredentialRevision
from app.domains.identity.schemas import WorldCredentialPurpose, WorldCredentialRead
from app.domains.identity.service.credential_resolution import CredentialResolver
from app.providers.image_profiles import MODEL_CATALOG
from app.providers.generation_profiles import validate_generation_profile
from app.domains.identity.service.world_credential_state import (
    find, metadata, _preserve_revision, _comfy_secrets,
)

PURPOSES = {
    "sns": CredentialPurpose.RESIDENT_LLM, "image": CredentialPurpose.USER_IMAGE,
    "chat": CredentialPurpose.MESSAGE_LLM, "vision": CredentialPurpose.IMAGE_INTERPRETATION,
    "consolidation": CredentialPurpose.MEMORY_CONSOLIDATION, "embedding": CredentialPurpose.MEMORY_EMBEDDING,
}


def validate_profile(purpose, provider, model, thinking):
    purpose = WorldCredentialPurpose(purpose)
    if purpose == "image":
        if thinking is not None or (f"{provider}:{model}" not in MODEL_CATALOG and not (provider == "comfyui" and model == "workflow")):
            raise CredentialResolutionError("world_credential_profile_invalid")
    elif provider not in {"google", "gemini", "google-generative-ai"}:
        raise CredentialResolutionError("world_credential_profile_invalid")
    elif purpose == "embedding":
        if model != "gemini-embedding-2" or thinking is not None:
            raise CredentialResolutionError("world_credential_profile_invalid")
    else:
        try:
            validate_generation_profile(model, thinking)
        except ValueError:
            raise CredentialResolutionError("world_credential_profile_invalid") from None








def find_revision(db, *, owner_id, world_id, world_character_id, purpose, credential_id, revision):
    """Authorize against the live actor, then read only the exact admitted revision."""
    current = find(db, owner_id=owner_id, world_id=world_id, world_character_id=world_character_id, purpose=purpose)
    if current is None or current.id != credential_id:
        raise CredentialResolutionError("world_credential_binding_changed")
    if current.revision == revision:
        return current
    prior = db.get(WorldCredentialRevision, (credential_id, revision), populate_existing=True)
    if prior is None:
        raise CredentialResolutionError("world_credential_revision_changed")
    return prior


def save(db, *, owner_id, world_id, world_character_id, purpose, data):
    validate_profile(purpose, data.provider, data.model, data.thinking_level)
    if (data.partner_api_key is not None or data.clear_partner_key) and (purpose != "image" or data.provider != "comfyui"):
        raise CredentialResolutionError("world_credential_profile_invalid")
    if purpose == "image":
        from .world_image_credentials import select_provider
        return select_provider(db, owner_id=owner_id, world_id=world_id, world_character_id=world_character_id, data=data)
    row = find(db, owner_id=owner_id, world_id=world_id, world_character_id=world_character_id, purpose=purpose)
    if data.expected_revision != (row.revision if row else 0):
        raise CredentialResolutionError("world_credential_revision_conflict")
    raw = data.api_key.get_secret_value().strip() if data.api_key is not None else ""
    if len(raw) > 4096:
        raise CredentialResolutionError("world_credential_too_long")
    if row is not None and row.provider != data.provider and row.encrypted_secret and not raw:
        if row.provider in {"google", "gemini", "google-generative-ai"} and data.provider in {"google", "gemini", "google-generative-ai"}:
            raw = security.decrypt_secret(row.encrypted_secret, scope=security.SecretScope(owner_id=owner_id,
                character_id=row.aad_character_id, provider=row.provider, purpose=row.aad_purpose)).strip()
        else:
            raise CredentialResolutionError("world_credential_provider_requires_key")
    if row is None:
        row = WorldCredential(id=uuid4().hex, owner_id=owner_id, world_id=world_id,
            world_character_id=world_character_id, purpose=purpose, provider=data.provider, model=data.model,
            thinking_level=data.thinking_level, revision=1, aad_character_id=world_character_id,
            aad_purpose=PURPOSES[purpose].value)
        db.add(row)
    else:
        _preserve_revision(db, row)
        result = db.execute(update(WorldCredential).where(WorldCredential.id == row.id,
            WorldCredential.revision == data.expected_revision).values(revision=row.revision + 1))
        if result.rowcount != 1:
            raise CredentialResolutionError("world_credential_revision_conflict")
        db.refresh(row)
        row.provider, row.model, row.thinking_level = data.provider, data.model, data.thinking_level
    if raw:
        row.encrypted_secret = security.encrypt_secret(raw, scope=security.SecretScope(owner_id=owner_id,
            character_id=row.aad_character_id, provider=row.provider, purpose=row.aad_purpose))
        row.fingerprint = security.fingerprint_secret(raw)
    db.flush()
    _preserve_revision(db, row)
    return metadata(row, purpose=purpose)


def delete(db, *, owner_id, world_id, world_character_id, purpose, expected_revision, provider=None, expected_key_revision=None):
    if purpose == "image":
        from .world_image_credentials import delete_provider
        from app.domains.identity.schemas import WorldCredentialDelete
        return delete_provider(db, owner_id=owner_id, world_id=world_id, world_character_id=world_character_id,
            data=WorldCredentialDelete(expected_revision=expected_revision, provider=provider,
                expected_key_revision=expected_key_revision))
    row = find(db, owner_id=owner_id, world_id=world_id, world_character_id=world_character_id, purpose=purpose)
    if row is None or row.revision != expected_revision:
        raise CredentialResolutionError("world_credential_revision_conflict")
    result = db.execute(update(WorldCredential).where(WorldCredential.id == row.id,
        WorldCredential.revision == expected_revision).values(encrypted_secret=None, fingerprint=None, revision=expected_revision + 1))
    if result.rowcount != 1:
        raise CredentialResolutionError("world_credential_revision_conflict")
    db.execute(sql_delete(WorldCredentialRevision).where(WorldCredentialRevision.credential_id == row.id))
    db.refresh(row)
    return metadata(row, purpose=purpose)




def resolve_image_keys(db, *, owner_id, world_id, world_character_id, revision=None):
    row = find(db, owner_id=owner_id, world_id=world_id, world_character_id=world_character_id, purpose="image")
    if row is None:
        raise CredentialResolutionError("world_credential_revision_changed")
    if revision is not None:
        row = find_revision(db, owner_id=owner_id, world_id=world_id, world_character_id=world_character_id,
            purpose="image", credential_id=row.id, revision=revision)
    validate_profile("image", row.provider, row.model, row.thinking_level)
    if row.provider == "comfyui" and not row.encrypted_secret:
        return None, None
    material = resolve(db, owner_id=owner_id, world_id=world_id, world_character_id=world_character_id,
        purpose="image", revision=revision, _image_envelope=True)
    if row.provider == "comfyui":
        secrets = _comfy_secrets(material.reveal())
        return None, secrets["partner"] or None
    return material, None


def resolve(db, *, owner_id, world_id, world_character_id, purpose, revision=None, _image_envelope=False):
    row = find(db, owner_id=owner_id, world_id=world_id, world_character_id=world_character_id, purpose=purpose)
    if row is None:
        raise CredentialResolutionError("world_credential_key_required")
    if revision is not None:
        row = find_revision(db, owner_id=owner_id, world_id=world_id, world_character_id=world_character_id,
            purpose=purpose, credential_id=row.id, revision=revision)
        if not row.encrypted_secret:
            raise CredentialResolutionError("world_credential_key_required")
    if not row.encrypted_secret:
        raise CredentialResolutionError("world_credential_key_required")
    validate_profile(purpose, row.provider, row.model, row.thinking_level)
    material = CredentialResolver.resolve_encrypted_material(encrypted_secret=row.encrypted_secret,
        credential_id=getattr(row, "credential_id", None) or row.id, provider=row.provider, model=row.model, fingerprint=row.fingerprint,
        purpose=PURPOSES[purpose], owner_id=owner_id, character_id=row.aad_character_id,
        stored_purpose=row.aad_purpose, thinking_level=row.thinking_level or "high")
    if purpose == "image" and material.provider == "comfyui" and not _image_envelope:
        return replace(material, _secret=_comfy_secrets(material.reveal())["key"])
    return replace(material, provider="google") if material.provider in {"gemini", "google-generative-ai"} else material
