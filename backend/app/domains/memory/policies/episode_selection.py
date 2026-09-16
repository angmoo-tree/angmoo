"""Validate source coverage before any canonical episode is accepted."""

from app.domains.memory.contracts.episode import (
    EpisodeBundle, EpisodeProposal, EpisodeSelection,
    MAX_EPISODE_CHARACTERS, MAX_EPISODES_PER_BUNDLE,
)
from app.domains.memory.exceptions import MemoryValidationError


def episode_response_schema() -> dict:
    refs = {"type": "array", "items": {"type": "string"}}
    return {
        "type": "object", "additionalProperties": False,
        "required": ["bundle_ref", "episodes", "skipped_new_refs", "needs_split"],
        "properties": {
            "bundle_ref": {"type": "string"},
            "episodes": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["summary", "source_refs", "follows_episode_refs"],
                "properties": {
                    "summary": {"type": "string"},
                    "source_refs": refs, "follows_episode_refs": refs,
                },
            }},
            "skipped_new_refs": refs, "needs_split": {"type": "boolean"},
        },
    }


def _refs(value: object, allowed: set[str]) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(ref, str) for ref in value):
        raise MemoryValidationError("episode_reference_invalid")
    if len(value) != len(set(value)) or not set(value) <= allowed:
        raise MemoryValidationError("episode_reference_invalid")
    return tuple(value)


def parse_episode_selection(payload: object, bundle: EpisodeBundle) -> EpisodeSelection:
    if not isinstance(payload, dict) or set(payload) != {"bundle_ref", "episodes", "skipped_new_refs", "needs_split"}:
        raise MemoryValidationError("episode_output_invalid")
    if payload["bundle_ref"] != bundle.bundle_ref or type(payload["needs_split"]) is not bool:
        raise MemoryValidationError("episode_output_invalid")
    rows = payload["episodes"]
    if not isinstance(rows, list) or len(rows) > MAX_EPISODES_PER_BUNDLE:
        raise MemoryValidationError("episode_output_invalid")
    new_refs = {f"S{i}" for i in range(1, len(bundle.new_units) + 1)}
    skipped = _refs(payload["skipped_new_refs"], new_refs)
    # A split response is not a partially accepted result. The caller must split
    # the unapplied input; no source becomes processed merely from this flag.
    if payload["needs_split"]:
        if rows or skipped:
            raise MemoryValidationError("episode_split_has_results")
        return EpisodeSelection((), (), needs_split=True)
    allowed = set(bundle.source_refs())
    priors = {f"P{i}" for i in range(1, len(bundle.prior_episodes) + 1)}
    used: set[str] = set()
    proposals = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"summary", "source_refs", "follows_episode_refs"}:
            raise MemoryValidationError("episode_output_invalid")
        summary = row["summary"]
        if not isinstance(summary, str) or not 1 <= len(summary.strip()) <= MAX_EPISODE_CHARACTERS:
            raise MemoryValidationError("episode_summary_invalid")
        refs = _refs(row["source_refs"], allowed)
        if not (set(refs) & new_refs):
            raise MemoryValidationError("episode_new_source_required")
        follows = _refs(row["follows_episode_refs"], priors)
        used.update(set(refs) & new_refs)
        proposals.append(EpisodeProposal(summary.strip(), refs, follows))
    if used & set(skipped) or used | set(skipped) != new_refs:
        raise MemoryValidationError("episode_source_coverage_incomplete")
    return EpisodeSelection(tuple(proposals), skipped)
