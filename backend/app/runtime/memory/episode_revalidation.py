"""Recheck a provider's frozen source ranges and own thoughts before persistence."""

from app.contracts.activity_thought import ActivityThought
from app.domains.memory.exceptions import MemoryConflictError
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader


def revalidate_episode_bundle(session, bundle):
    reader = RuntimeEpisodeDetailReader(session)
    units = tuple(bundle.source_refs().values())
    identities = tuple(dict.fromkeys((m.source_type, m.source_id) for u in units for m in u.members))
    sources = reader.read_sources(scope=bundle.scope, identities=identities)
    refs = tuple(dict.fromkeys(u.thought_reference for u in units if u.thought_reference))
    thoughts = reader.read_thoughts(scope=bundle.scope, references=refs)
    for unit in units:
        if unit.thought_reference:
            current = thoughts.get(unit.thought_reference)
            if current is None or current != unit.thought:
                raise MemoryConflictError("episode_apply_thought_changed")
        elif unit.thought != ActivityThought():
            raise MemoryConflictError("episode_apply_thought_unlinked")
        for member in unit.members:
            current = sources.get((member.source_type, member.source_id))
            if current is None:
                raise MemoryConflictError("episode_apply_source_missing")
            if (current.evidence.source_digest != member.source_digest
                or (member.total_characters is not None and len(current.text) != member.total_characters)
                or current.text[member.start_offset:member.start_offset + len(member.text)] != member.text):
                raise MemoryConflictError("episode_apply_source_changed")
    return {key: value.evidence for key, value in sources.items()}
