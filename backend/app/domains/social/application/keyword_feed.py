"""Bounded FTS5 lookup for the P5 interest-discovery lane."""

from __future__ import annotations

from dataclasses import dataclass

from app.domains.social.contracts import SocialSearchState, SocialSearchUnavailable
from app.domains.social.ports import SocialSearchIndexPort


@dataclass(frozen=True)
class KeywordPostLookup:
    post_ids: tuple[str, ...]
    raw_hit_count: int


def find_keyword_post_ids(
    search_index: SocialSearchIndexPort | None,
    *,
    search_state: SocialSearchState,
    world_id: str,
    keywords: tuple[str, str],
    per_keyword_limit: int,
    merged_limit: int,
) -> KeywordPostLookup:
    """Return ranked, deduplicated post IDs without consulting canonical SQL.

    FTS5 is only a rebuildable candidate finder.  Authorization, visibility,
    current membership, block state and deletion are deliberately revalidated
    against canonical SQLite by the caller.
    """

    if search_index is None or search_state is not SocialSearchState.READY:
        raise SocialSearchUnavailable(search_state)

    ordered_ids: list[str] = []
    seen: set[str] = set()
    raw_hit_count = 0
    try:
        for keyword in keywords:
            hits = search_index.search(
                world_id=world_id,
                query=keyword,
                limit=per_keyword_limit,
            )
            for hit in hits:
                raw_hit_count += 1
                if hit.world_id not in (None, world_id):
                    continue
                if hit.kind not in (None, "world_post"):
                    continue
                if hit.document_id in seen:
                    continue
                seen.add(hit.document_id)
                ordered_ids.append(hit.document_id)
                if len(ordered_ids) >= merged_limit:
                    return KeywordPostLookup(
                        post_ids=tuple(ordered_ids),
                        raw_hit_count=raw_hit_count,
                    )
    except SocialSearchUnavailable:
        raise
    except Exception as exc:
        raise SocialSearchUnavailable(SocialSearchState.UNAVAILABLE) from exc

    return KeywordPostLookup(
        post_ids=tuple(ordered_ids),
        raw_hit_count=raw_hit_count,
    )


__all__ = ["KeywordPostLookup", "find_keyword_post_ids"]
