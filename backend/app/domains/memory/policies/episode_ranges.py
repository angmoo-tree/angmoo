"""Lossless source ranges for a single activity larger than a prompt budget."""

from dataclasses import replace
import hashlib

from app.domains.memory.contracts.episode import EpisodeSourceUnit


def split_source_unit(unit: EpisodeSourceUnit, *, max_characters: int = 6_000) -> tuple[EpisodeSourceUnit, ...]:
    """Keep source IDs/revisions and explicit offsets, never mark a prefix complete.

    Splitting is a representation of one input unit, not new fictional activity.
    Application must persist every range decision before considering it handled.
    """
    if max_characters < 256:
        raise ValueError("episode_range_budget_invalid")
    if sum(len(member.text) for member in unit.members) <= max_characters:
        return (unit,)
    groups = []
    current = []
    used = 0
    for member in unit.members:
        offset = 0
        while offset < len(member.text):
            length = min(max_characters - used, len(member.text) - offset)
            current.append(replace(
                member, text=member.text[offset:offset + length],
                start_offset=member.start_offset + offset,
                total_characters=member.total_characters or member.start_offset + len(member.text),
            ))
            used += length
            offset += length
            if used == max_characters:
                groups.append(tuple(current))
                current, used = [], 0
    if current:
        groups.append(tuple(current))
    result = []
    for index, members in enumerate(groups):
        revision = hashlib.sha256(f"{unit.unit_revision}:ranges-v1:{max_characters}:{index}".encode()).hexdigest()
        result.append(replace(
            unit, unit_key=f"{unit.unit_key}:range:{index}", unit_revision=revision,
            members=members, coverage="partial_source",
        ))
    return tuple(result)
