from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.domains.character_lore import models, schemas
from app.domains.character_lore.constants import (
    APP_TIMEZONE,
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    MAX_LORE_CHUNKS_PER_CHARACTER,
    MAX_LORE_FILE_BYTES,
    MAX_LORE_SOURCES_PER_CHARACTER,
    MAX_LORE_TEXT_CHARS_PER_CHARACTER,
    RECENT_LORE_USAGE_LIMIT,
)
from app.domains.character_lore.contracts import (
    LoreCharacter,
    LoreChunkDraft,
    LoreOwner,
    LoreRetrievalResult,
    LoreWorkflows,
)
from app.domains.character_lore.contracts import (
    LoreEmbeddingTracker as RunLlmTracker,
)
from app.domains.character_lore.exceptions import (
    CharacterLoreEmbeddingError,
    CharacterLoreFileTooLargeError,
    CharacterLoreNotFoundError,
    CharacterLoreParserBusyError,
    CharacterLoreValidationError,
)
from app.domains.character_lore.parser import (
    _extract_text,
    _safe_filename,
    _validated_extension,
    validate_lore_upload_contract,
)
from app.domains.character_lore.policies.chunking import chunk_lore_text
from app.domains.character_lore.policies.ranking import _rerank_lore_candidates
from app.domains.character_lore.repository import (
    _chunk_count,
    _existing_embeddings_by_hash,
    _get_owned_source,
    _ready_chunk_count,
    _retrieve_lore_rows,
    _source_count,
    _total_text_chars,
)
from app.domains.character_lore.service import parser_quota as lore_parser_quota
from app.domains.character_lore.service.presentation import (
    _chunk_embedding_input,
    _query_embedding_input,
)
from app.domains.character_lore.utils import _sha256_text


def list_lore_sources(
    db: Session, user: LoreOwner, character_id: str, *, workflows: LoreWorkflows
) -> list[schemas.CharacterLoreSourceRead]:
    _get_owned_character(db, user, character_id, workflows=workflows)
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
    return [
        schemas.CharacterLoreSourceRead.model_validate(source) for source in sources
    ]


def lore_status(
    db: Session, user: LoreOwner, character_id: str, *, workflows: LoreWorkflows
) -> schemas.CharacterLoreStatusRead:
    _get_owned_character(db, user, character_id, workflows=workflows)
    return _status_read(db, character_id)


def upload_lore_source(
    db: Session,
    user: LoreOwner,
    character_id: str,
    *,
    filename: str,
    content_type: str | None,
    file_bytes: bytes,
    replace_existing: bool = False,
    workflows: LoreWorkflows,
) -> schemas.CharacterLoreSourceRead:
    extension = _validated_extension(filename)
    if len(file_bytes) > MAX_LORE_FILE_BYTES:
        raise CharacterLoreFileTooLargeError(
            "설정집 파일은 10 MiB 이하만 업로드할 수 있습니다."
        )
    validate_lore_upload_contract(
        extension=extension, content_type=content_type, file_bytes=file_bytes
    )
    character = _get_owned_character(db, user, character_id, workflows=workflows)
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
    if existing_sources and (not replace_existing):
        raise CharacterLoreValidationError(
            "앵무 1마리당 설정집 파일은 1개만 업로드할 수 있습니다. 기존 설정집을 삭제하거나 교체해 주세요."
        )
    drafts = chunk_lore_text(raw_text)
    replacing_text_chars = (
        sum((source.extracted_char_count for source in existing_sources))
        if replace_existing
        else 0
    )
    replacing_chunk_count = (
        sum((source.chunk_count for source in existing_sources))
        if replace_existing
        else 0
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
    _store_chunks_with_embeddings(
        db, character=character, source=source, drafts=drafts, workflows=workflows
    )
    db.commit()
    db.refresh(source)
    return schemas.CharacterLoreSourceRead.model_validate(source)


def delete_lore_source(
    db: Session,
    user: LoreOwner,
    character_id: str,
    source_id: str,
    *,
    workflows: LoreWorkflows,
) -> None:
    _get_owned_character(db, user, character_id, workflows=workflows)
    source = _get_owned_source(db, character_id=character_id, source_id=source_id)
    db.delete(source)
    db.commit()


def rebuild_lore_source(
    db: Session,
    user: LoreOwner,
    character_id: str,
    source_id: str,
    *,
    workflows: LoreWorkflows,
) -> schemas.CharacterLoreSourceRead:
    character = _get_owned_character(db, user, character_id, workflows=workflows)
    source = _get_owned_source(db, character_id=character.id, source_id=source_id)
    drafts = chunk_lore_text(source.raw_text)
    existing_text_chars = (
        _total_text_chars(db, character.id) - source.extracted_char_count
    )
    existing_chunk_count = _chunk_count(db, character.id) - source.chunk_count
    if existing_text_chars + len(source.raw_text) > MAX_LORE_TEXT_CHARS_PER_CHARACTER:
        raise CharacterLoreValidationError(
            "설정집 원문은 앵무당 최대 50,000자까지 가능합니다."
        )
    if existing_chunk_count + len(drafts) > MAX_LORE_CHUNKS_PER_CHARACTER:
        raise CharacterLoreValidationError(
            "설정집 chunk는 앵무당 최대 100개까지 가능합니다."
        )
    reusable = {
        chunk.content_hash: chunk.embedding
        for chunk in source.chunks
        if chunk.status == "ready"
        and chunk.embedding is not None
        and (chunk.embedding_model == EMBEDDING_MODEL)
        and (chunk.embedding_dimension == EMBEDDING_DIMENSION)
    }
    for chunk in list(source.chunks):
        db.delete(chunk)
    db.flush()
    source.chunk_count = len(drafts)
    source.status = "embedding_failed"
    source.error_message = None
    _store_chunks_with_embeddings(
        db,
        character=character,
        source=source,
        drafts=drafts,
        reusable_embeddings=reusable,
        workflows=workflows,
    )
    db.commit()
    db.refresh(source)
    return schemas.CharacterLoreSourceRead.model_validate(source)


def retrieve_lore_for_self_update(
    db: Session,
    *,
    character: LoreCharacter,
    now: datetime | None = None,
    workflows: LoreWorkflows,
) -> LoreRetrievalResult:
    query = build_lore_search_query(
        db, character=character, now=now, workflows=workflows
    )
    return retrieve_lore_for_query(
        db, character=character, query=query, workflows=workflows
    )


def has_ready_lore_chunks(db: Session, *, character_id: str) -> bool:
    return _ready_chunk_count(db, character_id) > 0


def retrieve_lore_for_query(
    db: Session, *, character: LoreCharacter, query: str, workflows: LoreWorkflows
) -> LoreRetrievalResult:
    clean_query = query.strip()
    if not clean_query or _ready_chunk_count(db, character.id) <= 0:
        return LoreRetrievalResult(mode="fallback_no_lore")
    try:
        credential = workflows.embedding_credential(db, character.id)
        query_embedding = workflows.embed_text(
            credential.api_key, _query_embedding_input(clean_query)
        )
        rows = _retrieve_lore_rows(
            db, character_id=character.id, query_embedding=query_embedding
        )
    except Exception as exc:
        return LoreRetrievalResult(
            mode="fallback_embedding_failed", error_message=str(exc)[:500]
        )
    return _lore_result_from_rows(rows)


async def retrieve_lore_for_query_tracked(
    db: Session,
    *,
    character: LoreCharacter,
    query: str,
    tracker: RunLlmTracker,
    agent_run_id: str,
    node: str = "CharacterLoreEmbedding",
    lane: str = "lore_query_embedding",
    workflows: LoreWorkflows,
) -> LoreRetrievalResult:
    clean_query = query.strip()
    if not clean_query or _ready_chunk_count(db, character.id) <= 0:
        return LoreRetrievalResult(mode="fallback_no_lore")
    try:
        credential = workflows.embedding_credential(db, character.id)
        context = workflows.embedding_context(
            credential_id=credential.credential_id,
            key_fingerprint=credential.key_fingerprint,
            character_id=character.id,
            agent_run_id=agent_run_id,
            node=node,
            lane=lane,
            provider=credential.provider,
            model=credential.model,
        )
        query_embedding = await workflows.embed_text_tracked(
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
            mode="fallback_embedding_failed", error_message=str(exc)[:500]
        )
    return _lore_result_from_rows(rows)


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
    character: LoreCharacter,
    now: datetime | None = None,
    workflows: LoreWorkflows,
) -> str:
    current_time = now or datetime.now(UTC)
    recent_topics = workflows.recent_topics(db, character_id=character.id)
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
    character: LoreCharacter,
    source: models.CharacterLoreSource,
    drafts: list[LoreChunkDraft],
    reusable_embeddings: dict[str, list[float]] | None = None,
    workflows: LoreWorkflows,
) -> None:
    reusable = dict(reusable_embeddings or {})
    reusable.update(_existing_embeddings_by_hash(db, character.id))
    api_key = ""
    embedding_error: str | None = None
    try:
        api_key = workflows.api_key(db, character.id)
    except CharacterLoreEmbeddingError as exc:
        embedding_error = str(exc)
    ready_count = 0
    for index, draft in enumerate(drafts):
        embedding = reusable.get(draft.content_hash)
        chunk_error = embedding_error
        if embedding is None and api_key:
            try:
                embedding = workflows.embed_text(api_key, _chunk_embedding_input(draft))
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
                embedding_dimension=EMBEDDING_DIMENSION
                if embedding is not None
                else None,
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
    db: Session, user: LoreOwner, character_id: str, *, workflows: LoreWorkflows
) -> LoreCharacter:
    character = workflows.get_character(db, character_id)
    if (
        character is None
        or character.deleted_at is not None
        or character.owner_id != user.id
    ):
        raise CharacterLoreNotFoundError(character_id)
    return character


def _ensure_character_limits(
    db: Session,
    *,
    character_id: str,
    new_text_chars: int,
    new_chunk_count: int,
    replacing_text_chars: int = 0,
    replacing_chunk_count: int = 0,
) -> None:
    current_text_chars = max(
        0, _total_text_chars(db, character_id) - replacing_text_chars
    )
    current_chunk_count = max(0, _chunk_count(db, character_id) - replacing_chunk_count)
    if current_text_chars + new_text_chars > MAX_LORE_TEXT_CHARS_PER_CHARACTER:
        raise CharacterLoreValidationError(
            "설정집 원문은 앵무당 최대 50,000자까지 가능합니다."
        )
    if current_chunk_count + new_chunk_count > MAX_LORE_CHUNKS_PER_CHARACTER:
        raise CharacterLoreValidationError(
            "설정집 chunk는 앵무당 최대 100개까지 가능합니다."
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
            f"- chunk_id={chunk.id}, source={source_name}, section={chunk.section_hint or '-'}, last_used_at={(chunk.last_used_at.isoformat() if chunk.last_used_at else '-')}, usage_count={chunk.usage_count}"
        )
    return "\n".join(lines)
