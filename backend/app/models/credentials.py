"""Compatibility facade for the canonical identity credential model."""

from app.domains.identity.infrastructure.sqlalchemy_credential_models import (
    LlmCredential,
)

__all__ = ["LlmCredential"]
