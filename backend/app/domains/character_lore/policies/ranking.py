from __future__ import annotations

import math
from datetime import UTC, datetime

from app.domains.character_lore.constants import (
    RECENT_LORE_SOFT_PENALTY_WINDOW,
    RECENT_LORE_STRONG_PENALTY_WINDOW,
    RETRIEVAL_FINAL_LIMIT,
)
from app.domains.character_lore.contracts import LoreRankedChunk, RetrievedLoreChunk


def _cosine_distance(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 1.0
    dot = sum((a * b for a, b in zip(left, right, strict=True)))
    left_norm = math.sqrt(sum((value * value for value in left)))
    right_norm = math.sqrt(sum((value * value for value in right)))
    if left_norm == 0.0 or right_norm == 0.0:
        return 1.0
    similarity = max(-1.0, min(1.0, dot / (left_norm * right_norm)))
    return 1.0 - similarity


def _rerank_lore_candidates(
    rows: list[tuple[LoreRankedChunk, float]],
) -> list[RetrievedLoreChunk]:
    now = datetime.now(UTC)
    scored: list[tuple[float, LoreRankedChunk, float]] = []
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

    def append_candidate(chunk: LoreRankedChunk, distance: float) -> None:
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
        if (
            chunk.section_hint
            and (chunk.source_id, chunk.section_hint) in used_sections
        ):
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
