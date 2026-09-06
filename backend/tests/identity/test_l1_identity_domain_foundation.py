from __future__ import annotations
import app.domains.identity.models as _actual_domains_identity_models
import app.domains.identity.schemas as _actual_domains_identity_schemas
from compatibility_retirement_support import export_matches


from model_fixture_support import models
from app.credentials import (
    CredentialMaterial,
    CredentialPurpose,
    CredentialResolutionError,
    CredentialResolver,
)
from app.credentials import contracts as legacy_contracts
from app.credentials import resolver as legacy_resolver
from app.domains.identity import models as legacy_auth_models
from app.domains.identity import models as legacy_credential_models


def test_legacy_model_imports_share_canonical_identity_objects() -> None:
    assert export_matches('app.domains.identity.public', 'User', models.User) and export_matches('app.domains.identity.public', 'User', legacy_auth_models.User)
    assert export_matches('app.domains.identity.public', 'AuthSession', models.AuthSession) and export_matches('app.domains.identity.public', 'AuthSession', legacy_auth_models.AuthSession)
    assert export_matches('app.domains.identity.public', 'AuthLoginThrottleBucket', models.AuthLoginThrottleBucket) and export_matches('app.domains.identity.public', 'AuthLoginThrottleBucket', legacy_auth_models.AuthLoginThrottleBucket)
    assert export_matches('app.domains.identity.public', 'AuthExternalVerificationReservation', models.AuthExternalVerificationReservation) and export_matches('app.domains.identity.public', 'AuthExternalVerificationReservation', legacy_auth_models.AuthExternalVerificationReservation)
    assert export_matches('app.domains.identity.public', 'AuthGoogleSignupGrant', models.AuthGoogleSignupGrant) and export_matches('app.domains.identity.public', 'AuthGoogleSignupGrant', legacy_auth_models.AuthGoogleSignupGrant)
    assert export_matches('app.domains.identity.public', 'CommunityMutationQuotaBucket', models.CommunityMutationQuotaBucket) and export_matches('app.domains.identity.public', 'CommunityMutationQuotaBucket', legacy_auth_models.CommunityMutationQuotaBucket)
    assert export_matches('app.domains.identity.public', 'LlmCredential', models.LlmCredential) and export_matches('app.domains.identity.public', 'LlmCredential', legacy_credential_models.LlmCredential)


def test_identity_model_table_contracts_are_unchanged() -> None:
    assert _actual_domains_identity_models.User.__tablename__ == 'users'
    assert _actual_domains_identity_models.AuthSession.__tablename__ == 'auth_sessions'
    assert _actual_domains_identity_models.LlmCredential.__tablename__ == 'llm_credentials'
    assert export_matches('app.domains.identity.public', 'User.__table__', legacy_auth_models.User.__table__)
    assert export_matches('app.domains.identity.public', 'LlmCredential.__table__', legacy_credential_models.LlmCredential.__table__)
    assert set(_actual_domains_identity_models.User.__table__.columns.keys()) == {'id', 'email', 'google_sub', 'password_hash', 'display_name', 'is_admin', 'display_name_normalized', 'display_name_updated_at', 'privacy_policy_agreed_at', 'terms_agreed_at', 'privacy_policy_version', 'terms_version', 'profile_setup_completed', 'feed_content_filter', 'created_at', 'deleted_at'}
    assert set(_actual_domains_identity_models.LlmCredential.__table__.columns.keys()) == {'id', 'owner_id', 'character_id', 'provider', 'purpose', 'model', 'auth_profile_id', 'label', 'encrypted_api_key', 'key_fingerprint', 'enabled', 'cooldown_until', 'created_at', 'updated_at'}


def test_legacy_schema_imports_share_canonical_identity_objects() -> None:
    assert export_matches('app.schemas', 'SignupCreate', _actual_domains_identity_schemas.SignupCreate) and export_matches('app.domains.identity.public', 'SignupCreate', _actual_domains_identity_schemas.SignupCreate) and export_matches('app.domains.identity.public', 'SignupCreate', _actual_domains_identity_schemas.SignupCreate) and export_matches('app.schemas.auth', 'SignupCreate', _actual_domains_identity_schemas.SignupCreate)
    assert export_matches('app.schemas', 'LoginCreate', _actual_domains_identity_schemas.LoginCreate) and export_matches('app.domains.identity.public', 'LoginCreate', _actual_domains_identity_schemas.LoginCreate) and export_matches('app.domains.identity.public', 'LoginCreate', _actual_domains_identity_schemas.LoginCreate) and export_matches('app.schemas.auth', 'LoginCreate', _actual_domains_identity_schemas.LoginCreate)
    assert export_matches('app.schemas', 'AuthRead', _actual_domains_identity_schemas.AuthRead) and export_matches('app.domains.identity.public', 'AuthRead', _actual_domains_identity_schemas.AuthRead) and export_matches('app.domains.identity.public', 'AuthRead', _actual_domains_identity_schemas.AuthRead) and export_matches('app.schemas.auth', 'AuthRead', _actual_domains_identity_schemas.AuthRead)
    assert export_matches('app.schemas', 'UserRead', _actual_domains_identity_schemas.UserRead) and export_matches('app.domains.identity.public', 'UserRead', _actual_domains_identity_schemas.UserRead) and export_matches('app.domains.identity.public', 'UserRead', _actual_domains_identity_schemas.UserRead) and export_matches('app.schemas.auth', 'UserRead', _actual_domains_identity_schemas.UserRead)
    assert export_matches('app.schemas', 'UserPreferencesUpdate', _actual_domains_identity_schemas.UserPreferencesUpdate) and export_matches('app.domains.identity.public', 'UserPreferencesUpdate', _actual_domains_identity_schemas.UserPreferencesUpdate) and export_matches('app.domains.identity.public', 'UserPreferencesUpdate', _actual_domains_identity_schemas.UserPreferencesUpdate) and export_matches('app.schemas.auth', 'UserPreferencesUpdate', _actual_domains_identity_schemas.UserPreferencesUpdate)


def test_credential_imports_share_canonical_identity_objects() -> None:
    assert export_matches('app.domains.identity.public', 'CredentialMaterial', CredentialMaterial)
    assert export_matches('app.domains.identity.public', 'CredentialPurpose', CredentialPurpose)
    assert export_matches('app.domains.identity.public', 'CredentialResolutionError', CredentialResolutionError)
    assert export_matches('app.domains.identity.public', 'CredentialResolver', CredentialResolver)
    assert export_matches('app.domains.identity.public', 'CredentialMaterial', legacy_contracts.CredentialMaterial)
    assert export_matches('app.domains.identity.public', 'CredentialPurpose', legacy_contracts.CredentialPurpose)
    assert export_matches('app.domains.identity.public', 'CredentialResolver', legacy_resolver.CredentialResolver)


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
