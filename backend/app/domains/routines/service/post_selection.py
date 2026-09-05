from __future__ import annotations

from app.domains.routines.contracts.post_selection import PostSelectionReferences


def _select_tick_post_id(
    references: PostSelectionReferences, *, preferred_post_id: str | None, character_id: str
) -> str | None:
    if preferred_post_id:
        return preferred_post_id
    post_id = references.get_latest_visible_nonself_root_id(character_id)
    if post_id:
        return post_id
    post_id = references.get_latest_visible_root_id()
    if post_id:
        return post_id
    return None


def _select_resident_run_post_id(
    references: PostSelectionReferences,
    *,
    preferred_post_id: str | None,
    character_id: str,
    scoped_runtime: bool,
) -> str | None:
    """Avoid inventing a global feed target for the scoped routine runtime."""
    if scoped_runtime and (
        references.routine_world_character_for_character(character_id=character_id)
        is not None
    ):
        return preferred_post_id
    return _select_tick_post_id(
        references,
        preferred_post_id=preferred_post_id,
        character_id=character_id,
    )
