from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.character_lore import models
from app.domains.character_lore.constants import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    RETRIEVAL_CANDIDATE_LIMIT,
)
from app.domains.character_lore.exceptions import CharacterLoreNotFoundError
from app.domains.character_lore.policies.ranking import _cosine_distance


def _retrieve_lore_rows(
    db: Session, *, character_id: str, query_embedding: list[float]
) -> list[tuple[models.CharacterLoreChunk, float]]:
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


def _get_owned_source(
    db: Session, *, character_id: str, source_id: str
) -> models.CharacterLoreSource:
    source = db.get(models.CharacterLoreSource, source_id)
    if source is None or source.character_id != character_id:
        raise CharacterLoreNotFoundError(source_id)
    return source


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
            select(
                func.coalesce(
                    func.sum(models.CharacterLoreSource.extracted_char_count), 0
                )
            ).where(models.CharacterLoreSource.character_id == character_id)
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


def _existing_embeddings_by_hash(
    db: Session, character_id: str
) -> dict[str, list[float]]:
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
