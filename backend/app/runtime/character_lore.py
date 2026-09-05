"""Compose Lore foreign lookups and the existing credential/provider transport."""

from __future__ import annotations
from app.domains.identity.repository import credentials as credential_repository

import asyncio
import time

from sqlalchemy.orm import Session

from app.cruds import agents as agent_crud
from app.domains.character_lore.constants import EMBEDDING_DIMENSION, EMBEDDING_MODEL
from app.domains.character_lore.contracts import (
    LoreWorkflows,
    _GoogleEmbeddingCredential,
)
from app.domains.character_lore.exceptions import CharacterLoreEmbeddingError
from app.domains.characters.service.profile import get_character
from app.domains.identity.contracts import CredentialPurpose
from app.domains.identity.exceptions import CredentialResolutionError
from app.domains.identity.service.credential_resolution import CredentialResolver
from app.integrations.direct_llm import (
    DirectLlmCallContext,
    RunLlmTracker,
    wait_for_provider_rate_limit,
)
from app.providers.contracts import EmbeddingRequest
from app.providers.registry import get_embedding_adapter
from app.services import community as community_service


def _google_embedding_credential_for_character(
    db: Session, character_id: str
) -> _GoogleEmbeddingCredential:
    credential = credential_repository.get_character_credential(db, character_id)
    try:
        material = CredentialResolver.resolve_llm_credential(
            credential,
            purpose=CredentialPurpose.LORE_EMBEDDING,
            character_id=character_id,
        )
        if material.provider != "google":
            raise CredentialResolutionError("credential provider is not Google")
        api_key = material.reveal()
    except CredentialResolutionError as exc:
        raise CharacterLoreEmbeddingError(
            "Google API key could not be decrypted."
        ) from exc
    return _GoogleEmbeddingCredential(
        api_key=api_key,
        credential_id=credential.id,
        key_fingerprint=credential.key_fingerprint,
        provider=credential.provider,
    )


def _google_api_key_for_character(db: Session, character_id: str) -> str:
    credential = credential_repository.get_character_credential(db, character_id)
    try:
        material = CredentialResolver.resolve_llm_credential(
            credential,
            purpose=CredentialPurpose.LORE_EMBEDDING,
            character_id=character_id,
        )
        if material.provider != "google":
            raise CredentialResolutionError("credential provider is not Google")
        return material.reveal()
    except CredentialResolutionError as exc:
        raise CharacterLoreEmbeddingError(
            "Google API key를 복호화하지 못했습니다."
        ) from exc


def _embed_text(api_key: str, text: str) -> list[float]:
    adapter = get_embedding_adapter("google", EMBEDDING_MODEL)
    try:
        return adapter.embed_sync(
            EmbeddingRequest(
                api_key=api_key,
                model=EMBEDDING_MODEL,
                text=text,
                output_dimension=EMBEDDING_DIMENSION,
            )
        )
    except Exception as exc:
        safe_error = adapter.normalize_error(exc, api_key=api_key)
        raise CharacterLoreEmbeddingError(str(safe_error)) from exc


async def _embed_text_tracked(
    api_key: str, text: str, *, context: DirectLlmCallContext, tracker: RunLlmTracker
) -> list[float]:
    await wait_for_provider_rate_limit(
        context=context, tracker=tracker, call_type="embed_content"
    )
    provider_call_order = tracker.next_provider_call_order()
    started = time.perf_counter()
    try:
        values = await asyncio.to_thread(_embed_text, api_key, text)
    except Exception as exc:
        tracker.record_embedding_call(
            context=context,
            provider_call_order=provider_call_order,
            status="error",
            duration_ms=int((time.perf_counter() - started) * 1000),
            failure_class=type(exc).__name__,
        )
        raise
    tracker.record_embedding_call(
        context=context,
        provider_call_order=provider_call_order,
        status="ok",
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
    return values


def build_lore_workflows() -> LoreWorkflows:
    return LoreWorkflows(
        get_character=get_character,
        embedding_credential=_google_embedding_credential_for_character,
        api_key=_google_api_key_for_character,
        embed_text=_embed_text,
        embed_text_tracked=_embed_text_tracked,
        embedding_context=DirectLlmCallContext,
        recent_topics=community_service.format_recent_own_root_topic_history_for_prompt,
    )
