from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core import security
from app.credentials import (
    CredentialPurpose,
    CredentialResolutionError,
    CredentialResolver,
)


def _credential(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": "credential-1",
        "owner_id": "user-1",
        "character_id": "character-1",
        "provider": "google",
        "purpose": "agent",
        "model": "gemini-3.1-flash-lite",
        "key_fingerprint": "fingerprint-1",
        "enabled": True,
    }
    values.update(overrides)
    if "encrypted_api_key" not in overrides:
        values["encrypted_api_key"] = security.encrypt_secret(
            "synthetic-api-key",
            scope=security.SecretScope(
                owner_id=str(values["owner_id"]),
                character_id=str(values["character_id"] or ""),
                provider=str(values["provider"]),
                purpose=str(values["purpose"]),
            ),
        )
    return SimpleNamespace(**values)


def test_resolver_returns_redacted_material_for_owned_character() -> None:
    material = CredentialResolver.resolve_llm_credential(
        _credential(),
        purpose=CredentialPurpose.RESIDENT_LLM,
        owner_id="user-1",
        character_id="character-1",
    )

    assert material.reveal() == "synthetic-api-key"
    assert material.fingerprint == "fingerprint-1"
    assert "synthetic-api-key" not in str(material)
    assert "synthetic-api-key" not in repr(material)
    assert "[REDACTED]" in repr(material)


@pytest.mark.parametrize(
    "overrides",
    [
        {"owner_id": "user-2"},
        {"character_id": "character-2"},
        {"purpose": "message"},
        {"enabled": False},
        {"encrypted_api_key": None},
    ],
)
def test_resolver_rejects_invalid_agent_credential(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(CredentialResolutionError):
        CredentialResolver.resolve_llm_credential(
            _credential(**overrides),
            purpose=CredentialPurpose.RESIDENT_LLM,
            owner_id="user-1",
            character_id="character-1",
        )


@pytest.mark.parametrize("stored_purpose", ["agent", "message"])
def test_message_resolver_accepts_agent_or_message_source(
    stored_purpose: str,
) -> None:
    material = CredentialResolver.resolve_llm_credential(
        _credential(purpose=stored_purpose),
        purpose=CredentialPurpose.MESSAGE_LLM,
        owner_id="user-1",
    )

    assert material.reveal() == "synthetic-api-key"
