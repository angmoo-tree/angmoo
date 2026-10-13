"""Deterministic mixed activity partitioning; no reads, writes or model calls."""
from dataclasses import replace

from app.domains.memory.contracts.activity_batch import ACTIVITY_POLICY_VERSION, MemoryActivity, chat_excerpt
from app.domains.memory.contracts.episode import EpisodeBundle
from app.domains.memory.exceptions import MemoryValidationError
from app.domains.memory.policies.episode_prompt import episode_prompt_payload


def excerpt_chat_unit(unit):
    if unit.kind != "chat_turn":
        return unit
    members = []
    for member in unit.members:
        excerpt = chat_excerpt(member.text)
        members.append(replace(member, text=excerpt.text, start_offset=0,
            total_characters=excerpt.total_characters, segments=excerpt.segments,
            omitted_characters=excerpt.omitted_characters, excerpt_policy=excerpt.policy,
            whole_hash=excerpt.whole_hash))
    return replace(unit, members=tuple(members), coverage="partial_source" if any(m.omitted_characters for m in members) else unit.coverage)


def partition_activity_units(units, *, previous_context=(), activation_epoch, cutoff_sequence, environment=None):
    """Assign every new source once. Preceding references never become new work."""
    if not units:
        return ()
    if len({u.unit_key for u in units}) != len(units):
        raise MemoryValidationError("episode_activity_duplicate")
    scope = units[0].scope
    if any(u.scope != scope for u in (*units, *previous_context)):
        raise MemoryValidationError("episode_activity_scope_invalid")
    groups = {}
    for unit in units:
        groups.setdefault(unit.thread_id if unit.kind == "chat_turn" else unit.unit_key, []).append(unit)
    entries = []
    for group, values in groups.items():
        def order(unit):
            sequence = max((int(member.source_id) for member in unit.members
                if member.source_type == "CHAT_MESSAGE" and member.role == "assistant" and member.source_id.isdigit()), default=0)
            return unit.occurred_at, sequence, unit.unit_key
        values = sorted(values, key=order)
        chat = values[0].kind == "chat_turn"
        history = [u for u in previous_context if u.thread_id == group] if chat else []
        for offset in range(0, len(values), 30 if chat else 1):
            fresh = tuple(excerpt_chat_unit(u) for u in values[offset:offset + (30 if chat else 1)])
            context = tuple(excerpt_chat_unit(u) for u in history[-5:]) if chat else ()
            activity = MemoryActivity(f"activity:{fresh[0].unit_key}", "chat" if chat else "sns",
                tuple(u.unit_key for u in fresh), tuple(u.unit_key for u in context), group if chat else None)
            entries.append((activity, fresh, context))
            history.extend(values[offset:offset + 30])
    entries.sort(key=lambda value: (value[1][0].occurred_at, value[0].activity_id))
    bundles = []
    start = 0
    while start < len(entries):
        chosen = None
        for end in range(start + 1, min(start + 32, len(entries)) + 1):
            part = entries[start:end]
            fresh = tuple(u for _, values, _ in part for u in values)
            fresh_keys = {u.unit_key for u in fresh}
            context = {u.unit_key: u for _, _, values in part for u in values if u.unit_key not in fresh_keys}
            bundle = EpisodeBundle(f"B{len(bundles) + 1}", scope, fresh, tuple(context.values()),
                activation_epoch=activation_epoch, cutoff_sequence=cutoff_sequence, environment=environment,
                policy_version=ACTIVITY_POLICY_VERSION, activities=tuple(a for a, _, _ in part))
            try:
                episode_prompt_payload(bundle)
            except MemoryValidationError as error:
                if str(error) != "episode_input_budget_exceeded" or chosen is None:
                    raise
                break
            chosen = bundle
        if chosen is None:
            raise MemoryValidationError("episode_input_budget_exceeded")
        bundles.append(chosen)
        start += len(chosen.activities)
    return tuple(bundles)
