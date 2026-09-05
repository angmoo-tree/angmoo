"""Compatibility facade for identity credential value objects."""

from app.domains.identity.contracts import CredentialMaterial
from app.domains.identity.contracts import CredentialPurpose

__all__ = ["CredentialMaterial", "CredentialPurpose"]
