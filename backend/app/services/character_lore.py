from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import math
import time
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app import models, schemas
from app.cruds import agents as agent_crud
from app.cruds import community as community_crud
from app.credentials import (
    CredentialPurpose,
    CredentialResolutionError,
    CredentialResolver,
)
from app.providers.contracts import EmbeddingRequest
from app.providers.registry import get_embedding_adapter
from app.services.direct_llm import (
    DirectLlmCallContext,
    RunLlmTracker,
    wait_for_provider_rate_limit,
)
from app.services import community as community_service
from app.domains.character_lore.service import parser_quota as lore_parser_quota
from app.domains.character_lore.constants import (
    SUPPORTED_EXTENSIONS,
    MAX_LORE_FILE_BYTES,
    LORE_UPLOAD_READ_CHUNK_BYTES,
    DOCX_CONTENT_TYPE,
    MAX_DOCX_ENTRIES,
    MAX_DOCX_UNCOMPRESSED_BYTES,
    MAX_DOCX_XML_BYTES,
    MAX_DOCX_ENTRY_BYTES,
    MAX_DOCX_COMPRESSION_RATIO,
    MAX_PDF_PAGES,
    MAX_PDF_OBJECTS,
    MAX_PARSED_TEXT_CHARS,
    LORE_PARSER_TIMEOUT_SECONDS,
    LORE_PARSER_MEMORY_BYTES,
    LORE_PARSER_CPU_SECONDS,
    MAX_LORE_SOURCES_PER_CHARACTER,
    MAX_LORE_TEXT_CHARS_PER_CHARACTER,
    MAX_LORE_CHUNKS_PER_CHARACTER,
    TARGET_CHUNK_MIN_CHARS,
    TARGET_CHUNK_TARGET_CHARS,
    TARGET_CHUNK_MAX_CHARS,
    EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
    RETRIEVAL_CANDIDATE_LIMIT,
    RETRIEVAL_FINAL_LIMIT,
    RECENT_LORE_USAGE_LIMIT,
    RECENT_LORE_STRONG_PENALTY_WINDOW,
    RECENT_LORE_SOFT_PENALTY_WINDOW,
    APP_TIMEZONE,
)
from app.domains.character_lore.exceptions import (
    CharacterLoreError,
    CharacterLoreNotFoundError,
    CharacterLoreValidationError,
    CharacterLoreFileTooLargeError,
    CharacterLoreEmbeddingError,
    CharacterLoreParserBusyError,
)
from app.domains.character_lore.contracts import (
    LoreChunkDraft,
    RetrievedLoreChunk,
    LoreRetrievalResult,
    _GoogleEmbeddingCredential,
)
from app.domains.character_lore.parser import (
    _apply_parser_resource_limits,
    _apply_windows_parser_resource_limits,
    _decode_text_file,
    _document_parser_worker,
    _extract_docx_text,
    _extract_docx_text_in_process,
    _extract_pdf_text,
    _extract_pdf_text_in_process,
    _extract_text,
    _preflight_docx,
    _run_document_parser,
    _run_worker_process,
    _safe_filename,
    _validated_extension,
    read_lore_upload_bytes,
    validate_lore_upload_contract,
)
from app.domains.character_lore.policies.chunking import (
    _clean_heading,
    _looks_like_boundary_line,
    _looks_like_section_heading,
    _split_long_unit,
    _split_lore_units,
    chunk_lore_text,
)
from app.domains.character_lore.utils import (
    _normalize_text,
    _sha256_text,
)
from app.domains.character_lore.service.presentation import (
    _chunk_embedding_input,
    _query_embedding_input,
    format_lore_prompt_context,
)


def list_lore_sources(
    db: Session, user: models.User, character_id: str
) -> list[schemas.CharacterLoreSourceRead]:
    _get_owned_character(db, user, character_id)
    sources = list(
        db.scalars(
            select(models.CharacterLoreSource)
            .where(models.CharacterLoreSource.character_id == character_id)
            .order_by(
                models.CharacterLoreSource.created_at.desc(),
                models.CharacterLoreSource.id.desc(),
            )
        )
    )
    return [schemas.CharacterLoreSourceRead.model_validate(source) for source in sources]


def lore_status(
    db: Session, user: models.User, character_id: str
) -> schemas.CharacterLoreStatusRead:
    _get_owned_character(db, user, character_id)
    return _status_read(db, character_id)


def upload_lore_source(
    db: Session,
    user: models.User,
    character_id: str,
    *,
    filename: str,
    content_type: str | None,
    file_bytes: bytes,
    replace_existing: bool = False,
) -> schemas.CharacterLoreSourceRead:
    extension = _validated_extension(filename)
    if len(file_bytes) > MAX_LORE_FILE_BYTES:
        raise CharacterLoreFileTooLargeError(
            "설정집 파일은 10 MiB 이하만 업로드할 수 있습니다."
        )
    validate_lore_upload_contract(
        extension=extension,
        content_type=content_type,
        file_bytes=file_bytes,
    )
    character = _get_owned_character(db, user, character_id)

    if extension in {".pdf", ".docx"}:
        try:
            with lore_parser_quota.parser_lease(db, user_id=user.id):
                raw_text = _extract_text(extension, file_bytes)
        except (
            lore_parser_quota.LoreParserCapacityError,
            lore_parser_quota.LoreParserLeaseUnavailableError,
        ) as exc:
            raise CharacterLoreParserBusyError(
                "Document parser capacity is temporarily unavailable"
            ) from exc
    else:
        raw_text = _extract_text(extension, file_bytes)
    raw_hash = _sha256_text(raw_text)
    existing = db.scalar(
        select(models.CharacterLoreSource)
        .where(
            models.CharacterLoreSource.character_id == character.id,
            models.CharacterLoreSource.raw_text_hash == raw_hash,
        )
        .limit(1)
    )
    if existing is not None:
        return schemas.CharacterLoreSourceRead.model_validate(existing)
    existing_sources = list(
        db.scalars(
            select(models.CharacterLoreSource).where(
                models.CharacterLoreSource.character_id == character.id
            )
        )
    )
    if existing_sources and not replace_existing:
        raise CharacterLoreValidationError(
            "앵무 1마리당 설정집 파일은 1개만 업로드할 수 있습니다. 기존 설정집을 삭제하거나 교체해 주세요."
        )

    drafts = chunk_lore_text(raw_text)
    replacing_text_chars = (
        sum(source.extracted_char_count for source in existing_sources)
        if replace_existing
        else 0
    )
    replacing_chunk_count = (
        sum(source.chunk_count for source in existing_sources) if replace_existing else 0
    )
    _ensure_character_limits(
        db,
        character_id=character.id,
        new_text_chars=len(raw_text),
        new_chunk_count=len(drafts),
        replacing_text_chars=replacing_text_chars,
        replacing_chunk_count=replacing_chunk_count,
    )
    for existing_source in existing_sources:
        db.delete(existing_source)
    source = models.CharacterLoreSource(
        id=f"lore-src-{uuid4().hex[:12]}",
        owner_id=user.id,
        character_id=character.id,
        filename=_safe_filename(filename),
        extension=extension.lstrip("."),
        content_type=(content_type or "")[:120] or None,
        file_size_bytes=len(file_bytes),
        raw_text=raw_text,
        raw_text_hash=raw_hash,
        extracted_char_count=len(raw_text),
        chunk_count=len(drafts),
        status="embedding_failed",
        error_message=None,
    )
    db.add(source)
    _store_chunks_with_embeddings(db, character=character, source=source, drafts=drafts)
    db.commit()
    db.refresh(source)
    return schemas.CharacterLoreSourceRead.model_validate(source)


def delete_lore_source(
    db: Session, user: models.User, character_id: str, source_id: str
) -> None:
    _get_owned_character(db, user, character_id)
    source = _get_owned_source(db, character_id=character_id, source_id=source_id)
    db.delete(source)
    db.commit()


def rebuild_lore_source(
    db: Session, user: models.User, character_id: str, source_id: str
) -> schemas.CharacterLoreSourceRead:
    character = _get_owned_character(db, user, character_id)
    source = _get_owned_source(db, character_id=character.id, source_id=source_id)
    drafts = chunk_lore_text(source.raw_text)
    existing_text_chars = _total_text_chars(db, character.id) - source.extracted_char_count
    existing_chunk_count = _chunk_count(db, character.id) - source.chunk_count
    if existing_text_chars + len(source.raw_text) > MAX_LORE_TEXT_CHARS_PER_CHARACTER:
        raise CharacterLoreValidationError("설정집 원문은 앵무당 최대 50,000자까지 가능합니다.")
    if existing_chunk_count + len(drafts) > MAX_LORE_CHUNKS_PER_CHARACTER:
        raise CharacterLoreValidationError("설정집 chunk는 앵무당 최대 100개까지 가능합니다.")
    reusable = {
        chunk.content_hash: chunk.embedding
        for chunk in source.chunks
        if chunk.status == "ready"
        and chunk.embedding is not None
        and chunk.embedding_model == EMBEDDING_MODEL
        and chunk.embedding_dimension == EMBEDDING_DIMENSION
    }
    for chunk in list(source.chunks):
        db.delete(chunk)
    db.flush()
    source.chunk_count = len(drafts)
    source.status = "embedding_failed"
    source.error_message = None
    _store_chunks_with_embeddings(
        db, character=character, source=source, drafts=drafts, reusable_embeddings=reusable
    )
    db.commit()
    db.refresh(source)
    return schemas.CharacterLoreSourceRead.model_validate(source)


def retrieve_lore_for_self_update(
    db: Session,
    *,
    character: models.Character,
    now: datetime | None = None,
) -> LoreRetrievalResult:
    query = build_lore_search_query(db, character=character, now=now)
    return retrieve_lore_for_query(db, character=character, query=query)


def has_ready_lore_chunks(db: Session, *, character_id: str) -> bool:
    return _ready_chunk_count(db, character_id) > 0


def retrieve_lore_for_query(
    db: Session,
    *,
    character: models.Character,
    query: str,
) -> LoreRetrievalResult:
    clean_query = query.strip()
    if not clean_query or _ready_chunk_count(db, character.id) <= 0:
        return LoreRetrievalResult(mode="fallback_no_lore")
    try:
        credential = _google_embedding_credential_for_character(db, character.id)
        query_embedding = _embed_text(
            credential.api_key, _query_embedding_input(clean_query)
        )
        rows = _retrieve_lore_rows(
            db, character_id=character.id, query_embedding=query_embedding
        )
    except Exception as exc:
        return LoreRetrievalResult(
            mode="fallback_embedding_failed",
            error_message=str(exc)[:500],
        )
    return _lore_result_from_rows(rows)


async def retrieve_lore_for_query_tracked(
    db: Session,
    *,
    character: models.Character,
    query: str,
    tracker: RunLlmTracker,
    agent_run_id: str,
    node: str = "CharacterLoreEmbedding",
    lane: str = "lore_query_embedding",
) -> LoreRetrievalResult:
    clean_query = query.strip()
    if not clean_query or _ready_chunk_count(db, character.id) <= 0:
        return LoreRetrievalResult(mode="fallback_no_lore")
    try:
        credential = _google_embedding_credential_for_character(db, character.id)
        context = DirectLlmCallContext(
            credential_id=credential.credential_id,
            key_fingerprint=credential.key_fingerprint,
            character_id=character.id,
            agent_run_id=agent_run_id,
            node=node,
            lane=lane,
            provider=credential.provider,
            model=credential.model,
        )
        query_embedding = await _embed_text_tracked(
            credential.api_key,
            _query_embedding_input(clean_query),
            context=context,
            tracker=tracker,
        )
        rows = _retrieve_lore_rows(
            db, character_id=character.id, query_embedding=query_embedding
        )
    except Exception as exc:
        return LoreRetrievalResult(
            mode="fallback_embedding_failed",
            error_message=str(exc)[:500],
        )
    return _lore_result_from_rows(rows)


def _retrieve_lore_rows(
    db: Session, *, character_id: str, query_embedding: list[float]
) -> list[tuple[models.CharacterLoreChunk, float]]:
    # A character is bounded to 100 lore chunks, so in-process cosine ranking
    # is deterministic and comfortably small.  This preserves retrieval
    # behavior without retaining a PostgreSQL/pgvector runtime dependency.
    chunks = list(
        db.scalars(
            select(models.CharacterLoreChunk)
            .join(models.CharacterLoreSource)
            .where(
                models.CharacterLoreChunk.character_id == character_id,
                models.CharacterLoreChunk.status == "ready",
                models.CharacterLoreChunk.embedding.is_not(None),
                models.CharacterLoreSource.status.in_(("ready", "partial")),
            )
            .order_by(models.CharacterLoreChunk.id)
        )
    )
    ranked = [
        (chunk, _cosine_distance(chunk.embedding or [], query_embedding))
        for chunk in chunks
    ]
    ranked.sort(key=lambda item: (item[1], item[0].id))
    return ranked[:RETRIEVAL_CANDIDATE_LIMIT]


def _cosine_distance(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 1.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 1.0
    similarity = max(-1.0, min(1.0, dot / (left_norm * right_norm)))
    return 1.0 - similarity


def _lore_result_from_rows(
    rows: list[tuple[models.CharacterLoreChunk, float]],
) -> LoreRetrievalResult:
    selected = _rerank_lore_candidates(rows)
    if not selected:
        return LoreRetrievalResult(mode="fallback_no_lore")
    return LoreRetrievalResult(mode="pgvector", chunks=tuple(selected))


def build_lore_search_query(
    db: Session,
    *,
    character: models.Character,
    now: datetime | None = None,
) -> str:
    current_time = now or datetime.now(UTC)
    recent_topics = community_service.format_recent_own_root_topic_history_for_prompt(
        db, character_id=character.id
    )
    recent_lore = _format_recent_lore_usage(db, character_id=character.id)
    return "\n".join(
        [
            "이 캐릭터가 특정 커뮤니티 글에 답하는 것이 아니라 독립 root 글로 쓸 만한 내부 소재를 찾는다.",
            f"현재 KST 시간대 참고: {current_time.astimezone(APP_TIMEZONE).isoformat()}",
            f"캐릭터 이름: {character.name}",
            f"기본 페르소나: {character.persona_summary or '-'}",
            f"성격: {character.personality or '-'}",
            f"말투: {character.speech_style or '-'}",
            f"세계관/배경: {character.worldview or '-'}",
            f"관심 주제: {character.topic_preferences or '-'}",
            "최근 자기 root 글 topic 이력:",
            recent_topics,
            "최근 사용한 설정집 소재:",
            recent_lore,
            "찾을 자료: 자기 생각, 기억, 취향, 습관, 장소, 물건, 고민, 관찰, 세계관 안의 작은 소재.",
        ]
    )


def mark_lore_chunks_used(db: Session, *, chunk_ids: list[str]) -> None:
    if not chunk_ids:
        return
    db.execute(
        update(models.CharacterLoreChunk)
        .where(models.CharacterLoreChunk.id.in_(chunk_ids))
        .values(
            last_used_at=datetime.now(UTC),
            usage_count=models.CharacterLoreChunk.usage_count + 1,
        )
    )
    db.commit()


def _store_chunks_with_embeddings(
    db: Session,
    *,
    character: models.Character,
    source: models.CharacterLoreSource,
    drafts: list[LoreChunkDraft],
    reusable_embeddings: dict[str, list[float]] | None = None,
) -> None:
    reusable = dict(reusable_embeddings or {})
    reusable.update(_existing_embeddings_by_hash(db, character.id))
    api_key = ""
    embedding_error: str | None = None
    try:
        api_key = _google_api_key_for_character(db, character.id)
    except CharacterLoreEmbeddingError as exc:
        embedding_error = str(exc)

    ready_count = 0
    for index, draft in enumerate(drafts):
        embedding = reusable.get(draft.content_hash)
        chunk_error = embedding_error
        if embedding is None and api_key:
            try:
                embedding = _embed_text(api_key, _chunk_embedding_input(draft))
                chunk_error = None
            except Exception as exc:
                chunk_error = str(exc)[:500]
        status = "ready" if embedding is not None else "embedding_failed"
        if status == "ready":
            ready_count += 1
        db.add(
            models.CharacterLoreChunk(
                id=f"lore-chunk-{uuid4().hex[:12]}",
                source_id=source.id,
                owner_id=character.owner_id,
                character_id=character.id,
                chunk_index=index,
                section_hint=draft.section_hint,
                text=draft.text,
                content_hash=draft.content_hash,
                embedding=embedding,
                embedding_model=EMBEDDING_MODEL if embedding is not None else None,
                embedding_dimension=EMBEDDING_DIMENSION if embedding is not None else None,
                status=status,
                error_message=chunk_error,
                usage_count=0,
            )
        )
    if ready_count == len(drafts):
        source.status = "ready"
        source.error_message = None
    elif ready_count > 0:
        source.status = "partial"
        source.error_message = "일부 chunk embedding에 실패했습니다."
    else:
        source.status = "embedding_failed"
        source.error_message = embedding_error or "설정집 embedding에 실패했습니다."


def _get_owned_character(
    db: Session, user: models.User, character_id: str
) -> models.Character:
    character = community_crud.get_character(db, character_id)
    if character is None or character.deleted_at is not None or character.owner_id != user.id:
        raise CharacterLoreNotFoundError(character_id)
    return character


def _get_owned_source(
    db: Session, *, character_id: str, source_id: str
) -> models.CharacterLoreSource:
    source = db.get(models.CharacterLoreSource, source_id)
    if source is None or source.character_id != character_id:
        raise CharacterLoreNotFoundError(source_id)
    return source


def _ensure_character_limits(
    db: Session,
    *,
    character_id: str,
    new_text_chars: int,
    new_chunk_count: int,
    replacing_text_chars: int = 0,
    replacing_chunk_count: int = 0,
) -> None:
    current_text_chars = max(0, _total_text_chars(db, character_id) - replacing_text_chars)
    current_chunk_count = max(0, _chunk_count(db, character_id) - replacing_chunk_count)
    if current_text_chars + new_text_chars > MAX_LORE_TEXT_CHARS_PER_CHARACTER:
        raise CharacterLoreValidationError("설정집 원문은 앵무당 최대 50,000자까지 가능합니다.")
    if current_chunk_count + new_chunk_count > MAX_LORE_CHUNKS_PER_CHARACTER:
        raise CharacterLoreValidationError("설정집 chunk는 앵무당 최대 100개까지 가능합니다.")


def _source_count(db: Session, character_id: str) -> int:
    return int(
        db.scalar(
            select(func.count(models.CharacterLoreSource.id)).where(
                models.CharacterLoreSource.character_id == character_id
            )
        )
        or 0
    )


def _total_text_chars(db: Session, character_id: str) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(models.CharacterLoreSource.extracted_char_count), 0))
            .where(models.CharacterLoreSource.character_id == character_id)
        )
        or 0
    )


def _chunk_count(db: Session, character_id: str) -> int:
    return int(
        db.scalar(
            select(func.count(models.CharacterLoreChunk.id)).where(
                models.CharacterLoreChunk.character_id == character_id
            )
        )
        or 0
    )


def _ready_chunk_count(db: Session, character_id: str) -> int:
    return int(
        db.scalar(
            select(func.count(models.CharacterLoreChunk.id)).where(
                models.CharacterLoreChunk.character_id == character_id,
                models.CharacterLoreChunk.status == "ready",
            )
        )
        or 0
    )


def _status_read(db: Session, character_id: str) -> schemas.CharacterLoreStatusRead:
    source_count = _source_count(db, character_id)
    ready_source_count = int(
        db.scalar(
            select(func.count(models.CharacterLoreSource.id)).where(
                models.CharacterLoreSource.character_id == character_id,
                models.CharacterLoreSource.status.in_(("ready", "partial")),
            )
        )
        or 0
    )
    chunk_count = _chunk_count(db, character_id)
    ready_chunk_count = _ready_chunk_count(db, character_id)
    return schemas.CharacterLoreStatusRead(
        character_id=character_id,
        source_count=source_count,
        ready_source_count=ready_source_count,
        chunk_count=chunk_count,
        ready_chunk_count=ready_chunk_count,
        max_sources=MAX_LORE_SOURCES_PER_CHARACTER,
        max_text_chars=MAX_LORE_TEXT_CHARS_PER_CHARACTER,
        max_chunks=MAX_LORE_CHUNKS_PER_CHARACTER,
        max_file_bytes=MAX_LORE_FILE_BYTES,
    )


def _google_embedding_credential_for_character(
    db: Session, character_id: str
) -> _GoogleEmbeddingCredential:
    credential = agent_crud.get_character_credential(db, character_id)
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
        raise CharacterLoreEmbeddingError("Google API key could not be decrypted.") from exc
    return _GoogleEmbeddingCredential(
        api_key=api_key,
        credential_id=credential.id,
        key_fingerprint=credential.key_fingerprint,
        provider=credential.provider,
    )


def _google_api_key_for_character(db: Session, character_id: str) -> str:
    credential = agent_crud.get_character_credential(db, character_id)
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
        raise CharacterLoreEmbeddingError("Google API key를 복호화하지 못했습니다.") from exc


def _existing_embeddings_by_hash(db: Session, character_id: str) -> dict[str, list[float]]:
    rows = db.scalars(
        select(models.CharacterLoreChunk).where(
            models.CharacterLoreChunk.character_id == character_id,
            models.CharacterLoreChunk.status == "ready",
            models.CharacterLoreChunk.embedding.is_not(None),
            models.CharacterLoreChunk.embedding_model == EMBEDDING_MODEL,
            models.CharacterLoreChunk.embedding_dimension == EMBEDDING_DIMENSION,
        )
    )
    result: dict[str, list[float]] = {}
    for chunk in rows:
        if chunk.content_hash not in result and chunk.embedding is not None:
            result[chunk.content_hash] = list(chunk.embedding)
    return result


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
    api_key: str,
    text: str,
    *,
    context: DirectLlmCallContext,
    tracker: RunLlmTracker,
) -> list[float]:
    await wait_for_provider_rate_limit(
        context=context,
        tracker=tracker,
        call_type="embed_content",
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


def _format_recent_lore_usage(db: Session, *, character_id: str) -> str:
    chunks = list(
        db.scalars(
            select(models.CharacterLoreChunk)
            .where(
                models.CharacterLoreChunk.character_id == character_id,
                models.CharacterLoreChunk.last_used_at.is_not(None),
            )
            .order_by(
                models.CharacterLoreChunk.last_used_at.desc(),
                models.CharacterLoreChunk.id.desc(),
            )
            .limit(RECENT_LORE_USAGE_LIMIT)
        )
    )
    if not chunks:
        return "- none"
    lines = []
    for chunk in chunks:
        source_name = chunk.source.filename if chunk.source else "-"
        lines.append(
            f"- chunk_id={chunk.id}, source={source_name}, section={chunk.section_hint or '-'}, "
            f"last_used_at={chunk.last_used_at.isoformat() if chunk.last_used_at else '-'}, "
            f"usage_count={chunk.usage_count}"
        )
    return "\n".join(lines)


def _rerank_lore_candidates(rows: list[tuple[models.CharacterLoreChunk, float]]) -> list[RetrievedLoreChunk]:
    now = datetime.now(UTC)
    scored: list[tuple[float, models.CharacterLoreChunk, float]] = []
    for chunk, raw_distance in rows:
        distance = float(raw_distance or 0.0)
        penalty = min(0.2, max(0, chunk.usage_count) * 0.02)
        if chunk.last_used_at is not None:
            age = now - chunk.last_used_at
            if age <= RECENT_LORE_STRONG_PENALTY_WINDOW:
                penalty += 0.35
            elif age <= RECENT_LORE_SOFT_PENALTY_WINDOW:
                penalty += 0.18
        scored.append((distance + penalty, chunk, distance))
    scored.sort(key=lambda item: (item[0], item[1].usage_count, item[1].chunk_index))

    selected: list[RetrievedLoreChunk] = []
    used_sources: set[str] = set()
    used_sections: set[tuple[str, str]] = set()

    def append_candidate(chunk: models.CharacterLoreChunk, distance: float) -> None:
        selected.append(
            RetrievedLoreChunk(
                id=chunk.id,
                source_id=chunk.source_id,
                source_filename=chunk.source.filename if chunk.source else "-",
                section_hint=chunk.section_hint,
                text=chunk.text,
                distance=distance,
            )
        )
        used_sources.add(chunk.source_id)
        if chunk.section_hint:
            used_sections.add((chunk.source_id, chunk.section_hint))

    for _, chunk, distance in scored:
        if len(selected) >= RETRIEVAL_FINAL_LIMIT:
            break
        if chunk.source_id in used_sources and len(selected) < 2:
            continue
        if chunk.section_hint and (chunk.source_id, chunk.section_hint) in used_sections:
            continue
        append_candidate(chunk, distance)

    if len(selected) < min(3, len(scored)):
        selected_ids = {chunk.id for chunk in selected}
        for _, chunk, distance in scored:
            if len(selected) >= RETRIEVAL_FINAL_LIMIT:
                break
            if chunk.id in selected_ids:
                continue
            append_candidate(chunk, distance)
            selected_ids.add(chunk.id)
    return selected


