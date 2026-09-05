"""Credential resolution and direct-LLM request identity for routine generation."""
from __future__ import annotations
from typing import Any
from app.credentials import CredentialPurpose, CredentialResolutionError, CredentialResolver
from app.integrations.direct_llm import DirectLlmCallContext, DirectLlmError


def _api_key(credential: Any) -> str:
    try:
        return CredentialResolver.resolve_llm_credential(
            credential,
            purpose=CredentialPurpose.RESIDENT_LLM,
        ).reveal()
    except CredentialResolutionError as exc:
        raise DirectLlmError("credential key cannot be decrypted") from exc


def _llm_context(
    ctx: Any, *, node: str, lane: str
) -> DirectLlmCallContext:
    return DirectLlmCallContext(
        credential_id=ctx.credential.id,
        character_id=ctx.character.id,
        agent_run_id=ctx.run_id,
        node=node,
        lane=lane,
        provider=ctx.credential.provider,
        model=ctx.credential.model,
        key_fingerprint=ctx.credential.key_fingerprint,
    )
