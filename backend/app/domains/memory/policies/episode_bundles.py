"""Partition prevalidated source snapshots without guessing response pairing."""

import hashlib
import json

from app.domains.memory.contracts.episode import (
    EpisodeBundle, EpisodeSourceUnit, MAX_NEW_CHAT_TURNS, MAX_CONTEXT_CHAT_TURNS,
    MAX_NEW_SOCIAL_UNITS,
)
from app.domains.memory.exceptions import MemoryValidationError
from app.domains.memory.policies.episode_prompt import episode_prompt_payload


def bundle_manifest_hash(bundle: EpisodeBundle) -> str:
    """Cover all inputs, including context/skipped candidates and the cutoff."""
    manifest = {
        "policy": "episode-selection.v1",
        "scope": [bundle.scope.owner_id, bundle.scope.world_id, bundle.scope.subject_world_character_id],
        "epoch": bundle.activation_epoch, "cutoff": bundle.cutoff_sequence,
        "sources": [(ref, unit.unit_key, unit.unit_revision, unit.thread_id,
                     [(m.source_type, m.source_id, m.source_digest, m.role, m.start_offset, m.total_characters,
                       hashlib.sha256(m.text.encode()).hexdigest(), m.actor_label, m.occurred_at) for m in unit.members],
                     unit.thought_reference, unit.thought.text, unit.thought.status, unit.thought.truncated,
                     unit.legacy_subjective_context)
                    for ref, unit in bundle.source_refs().items()],
        "priors": [(p.item_id, p.item_version, p.summary) for p in bundle.prior_episodes],
    }
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def partition_episode_units(
    units: tuple[EpisodeSourceUnit, ...], *,
    previous_context: tuple[EpisodeSourceUnit, ...] = (),
    activation_epoch: str, cutoff_sequence: int,
) -> tuple[EpisodeBundle, ...]:
    """A caller provides one scope/thread and only committed, unprocessed units.

    Oversized single units explicitly require the source-range preparation
    path. This function never silently marks a truncated source processed.
    """
    if not units:
        return ()
    is_chat = units[0].kind == "chat_turn"
    limit = MAX_NEW_CHAT_TURNS if is_chat else MAX_NEW_SOCIAL_UNITS
    all_units = (*previous_context, *units)
    if len({u.unit_key for u in all_units}) != len(all_units):
        raise MemoryValidationError("episode_partition_duplicate_unit")
    first = units[0]
    if any(u.scope != first.scope or u.thread_id != first.thread_id or (u.kind == "chat_turn") != is_chat for u in all_units):
        raise MemoryValidationError("episode_partition_scope_mismatch")
    result = []
    offset = 0
    while offset < len(units):
        history = (*previous_context, *units[:offset])
        context = history[-MAX_CONTEXT_CHAT_TURNS:] if is_chat else ()
        end = min(len(units), offset + limit)
        while True:
            bundle = EpisodeBundle(
                bundle_ref=f"B{len(result) + 1}", scope=first.scope,
                new_units=units[offset:end], context_units=context,
                activation_epoch=activation_epoch, cutoff_sequence=cutoff_sequence,
            )
            try:
                episode_prompt_payload(bundle)
                break
            except MemoryValidationError as exc:
                if str(exc) != "episode_input_budget_exceeded":
                    raise
                if end > offset + 1:
                    end -= 1
                elif context:
                    context = context[1:]
                else:
                    raise MemoryValidationError("episode_source_range_split_required") from None
        result.append(bundle)
        offset = end
    return tuple(result)
