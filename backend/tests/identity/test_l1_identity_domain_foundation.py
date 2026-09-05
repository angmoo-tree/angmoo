from __future__ import annotations

from app import models, schemas
from app.credentials import (
    CredentialMaterial,
    CredentialPurpose,
    CredentialResolutionError,
    CredentialResolver,
)
from app.credentials import contracts as legacy_contracts
from app.credentials import resolver as legacy_resolver
from app.domains.identity import public as identity
from app.models import auth as legacy_auth_models
from app.models import credentials as legacy_credential_models
from app.schemas import auth as legacy_auth_schemas


def test_legacy_model_imports_share_canonical_identity_objects() -> None:
    assert models.User is identity.User is legacy_auth_models.User
    assert models.AuthSession is identity.AuthSession is legacy_auth_models.AuthSession
    assert (
        models.AuthLoginThrottleBucket
        is identity.AuthLoginThrottleBucket
        is legacy_auth_models.AuthLoginThrottleBucket
    )
    assert (
        models.AuthExternalVerificationReservation
        is identity.AuthExternalVerificationReservation
        is legacy_auth_models.AuthExternalVerificationReservation
    )
    assert (
        models.AuthGoogleSignupGrant
        is identity.AuthGoogleSignupGrant
        is legacy_auth_models.AuthGoogleSignupGrant
    )
    assert (
        models.CommunityMutationQuotaBucket
        is identity.CommunityMutationQuotaBucket
        is legacy_auth_models.CommunityMutationQuotaBucket
    )
    assert (
        models.LlmCredential
        is identity.LlmCredential
        is legacy_credential_models.LlmCredential
    )


def test_identity_model_table_contracts_are_unchanged() -> None:
    assert identity.User.__tablename__ == "users"
    assert identity.AuthSession.__tablename__ == "auth_sessions"
    assert identity.LlmCredential.__tablename__ == "llm_credentials"
    assert identity.User.__table__ is legacy_auth_models.User.__table__
    assert (
        identity.LlmCredential.__table__
        is legacy_credential_models.LlmCredential.__table__
    )
    assert set(identity.User.__table__.columns.keys()) == {
        "id",
        "email",
        "google_sub",
        "password_hash",
        "display_name",
        "is_admin",
        "display_name_normalized",
        "display_name_updated_at",
        "privacy_policy_agreed_at",
        "terms_agreed_at",
        "privacy_policy_version",
        "terms_version",
        "profile_setup_completed",
        "feed_content_filter",
        "created_at",
        "deleted_at",
    }
    assert set(identity.LlmCredential.__table__.columns.keys()) == {
        "id",
        "owner_id",
        "character_id",
        "provider",
        "purpose",
        "model",
        "auth_profile_id",
        "label",
        "encrypted_api_key",
        "key_fingerprint",
        "enabled",
        "cooldown_until",
        "created_at",
        "updated_at",
    }


def test_legacy_schema_imports_share_canonical_identity_objects() -> None:
    assert schemas.SignupCreate is identity.SignupCreate is legacy_auth_schemas.SignupCreate
    assert schemas.LoginCreate is identity.LoginCreate is legacy_auth_schemas.LoginCreate
    assert schemas.AuthRead is identity.AuthRead is legacy_auth_schemas.AuthRead
    assert schemas.UserRead is identity.UserRead is legacy_auth_schemas.UserRead
    assert (
        schemas.UserPreferencesUpdate
        is identity.UserPreferencesUpdate
        is legacy_auth_schemas.UserPreferencesUpdate
    )


def test_credential_imports_share_canonical_identity_objects() -> None:
    assert CredentialMaterial is identity.CredentialMaterial
    assert CredentialPurpose is identity.CredentialPurpose
    assert CredentialResolutionError is identity.CredentialResolutionError
    assert CredentialResolver is identity.CredentialResolver
    assert legacy_contracts.CredentialMaterial is identity.CredentialMaterial
    assert legacy_contracts.CredentialPurpose is identity.CredentialPurpose
    assert legacy_resolver.CredentialResolver is identity.CredentialResolver


def test_credential_material_repr_does_not_expose_secret() -> None:
    material = CredentialMaterial(
        credential_id="credential-1",
        provider="google",
        model="gemini-3.1-flash-lite",
        fingerprint="fingerprint-1",
        purpose=CredentialPurpose.RESIDENT_LLM,
        _secret="do-not-print-this",
    )

    assert "do-not-print-this" not in repr(material)
    assert "do-not-print-this" not in str(material)
    assert "[REDACTED]" in repr(material)
    assert material.reveal() == "do-not-print-this"
