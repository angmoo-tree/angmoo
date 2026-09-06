from __future__ import annotations

from app.core.context_text import neutralize_context_text
from app.domains.character_lore.contracts import LoreChunkDraft, LoreRetrievalResult


def format_lore_prompt_context(
    result: LoreRetrievalResult,
    *,
    lore_query_mode: str | None = None,
    max_chunks: int | None = None,
    max_text_chars: int = 900,
) -> str:
    if not result.chunks:
        return ""
    chunks = result.chunks[:max_chunks] if max_chunks is not None else result.chunks
    lines = [
        "Character lore retrieval:",
        f"- retrieval_mode: {result.mode}",
        f"- lore_query_mode: {lore_query_mode}" if lore_query_mode else "",
        "- These chunks are private reference material. Do not copy sentences from them into title/body.",
        "- Use them only to choose a character-owned thought, memory, habit, taste, object, place, or worldview detail.",
        "- Do not write as if replying to a specific community post or author.",
        "- Do not expose lore_chunk_ids, retrieval_mode, lore_query_mode, or source filenames in visible title/body.",
        "selected_lore_chunks:",
    ]
    lines = [line for line in lines if line]
    for chunk in chunks:
        lines.extend(
            [
                f"- lore_chunk_id: {chunk.id}",
                f"  source: {neutralize_context_text(chunk.source_filename)}",
                f"  section_hint: {neutralize_context_text(chunk.section_hint or '-')}",
                "  text: " + neutralize_context_text(chunk.text)[:max_text_chars],
            ]
        )
    return "\n".join(lines)


def _chunk_embedding_input(draft: LoreChunkDraft) -> str:
    return f"title: {draft.section_hint or 'none'} | text: {draft.text}"


def _query_embedding_input(query: str) -> str:
    return f"task: search result | query: {query}"
