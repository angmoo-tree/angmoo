"""Compatibility facade for identity credential resolution."""

from app.domains.identity.service.credential_resolution import CredentialResolutionError
from app.domains.identity.service.credential_resolution import CredentialResolver

__all__ = ["CredentialResolutionError", "CredentialResolver"]
