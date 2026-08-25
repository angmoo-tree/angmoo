"""Deterministic, overwrite-free World Package import collision planning."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
import unicodedata


class WorldPackageDuplicateState(StrEnum):
    NEW_PACKAGE = "new_package"
    ALREADY_IMPORTED = "already_imported"
    INDEPENDENT_FORK = "independent_fork"


@dataclass(frozen=True, slots=True)
class WorldPackageCharacterCollision:
    source_ref: str
    display_name: str
    planned_handle: str


@dataclass(frozen=True, slots=True)
class WorldPackageCollisionPlan:
    planned_world_slug: str
    characters: tuple[WorldPackageCharacterCollision, ...]
    duplicate_state: WorldPackageDuplicateState
    commit_allowed_by_default: bool


_SLUG_SEPARATORS = re.compile(r"[^a-z0-9]+")
_HANDLE_SEPARATORS = re.compile(r"[^a-z0-9_]+")


def plan_world_package_collisions(
    *,
    world_name: str,
    character_hints: tuple[tuple[str, str, str], ...],
    content_digest: str,
    existing_world_slugs: frozenset[str],
    existing_character_handles: frozenset[str],
    duplicate_state: WorldPackageDuplicateState,
) -> WorldPackageCollisionPlan:
    slug_base = _ascii_token(world_name, separator="-")[:72]
    if not slug_base:
        slug_base = f"world-{content_digest[:12]}"
    planned_slug = _available_slug(slug_base, set(existing_world_slugs))

    occupied_handles = set(existing_character_handles)
    planned_characters: list[WorldPackageCharacterCollision] = []
    for source_ref, display_name, handle_hint in character_hints:
        handle_base = _ascii_token(handle_hint, separator="_")[:34]
        if not handle_base:
            handle_base = f"character_{content_digest[:8]}"
        planned_handle = _available_handle(handle_base, occupied_handles)
        occupied_handles.add(planned_handle)
        planned_characters.append(
            WorldPackageCharacterCollision(
                source_ref=source_ref,
                display_name=display_name,
                planned_handle=planned_handle,
            )
        )

    return WorldPackageCollisionPlan(
        planned_world_slug=planned_slug,
        characters=tuple(planned_characters),
        duplicate_state=duplicate_state,
        commit_allowed_by_default=(
            duplicate_state is not WorldPackageDuplicateState.ALREADY_IMPORTED
        ),
    )


def _ascii_token(value: str, *, separator: str) -> str:
    normalized = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    pattern = _SLUG_SEPARATORS if separator == "-" else _HANDLE_SEPARATORS
    return pattern.sub(separator, normalized).strip(separator)


def _available_slug(base: str, occupied: set[str]) -> str:
    candidate = base
    suffix = 1
    while candidate in occupied:
        suffix += 1
        marker = f"-{suffix}"
        candidate = f"{base[: max(1, 96 - len(marker))]}{marker}"
    return candidate


def _available_handle(base: str, occupied: set[str]) -> str:
    candidate = base
    suffix = 1
    while candidate in occupied:
        suffix += 1
        marker = f"_{suffix}"
        candidate = f"{base[: 40 - len(marker)]}{marker}"
    return candidate


__all__ = [
    "WorldPackageCharacterCollision",
    "WorldPackageCollisionPlan",
    "WorldPackageDuplicateState",
    "plan_world_package_collisions",
]
