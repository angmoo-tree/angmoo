"""Validate captured bundle scope; never reread historical sources or thoughts."""
from datetime import datetime
from app.domains.memory.exceptions import MemoryConflictError
from app.domains.memory.contracts.source_evidence import CanonicalMemoryEvidence
from app.domains.memory.contracts.provenance import MemorySourceTypeV1


def revalidate_episode_bundle(session, bundle):
    sources = {}
    for unit in bundle.source_refs().values():
        if unit.scope != bundle.scope:
            raise MemoryConflictError("episode_apply_scope_invalid")
        for member in unit.members:
            sources[(member.source_type, member.source_id)] = CanonicalMemoryEvidence(
                MemorySourceTypeV1(member.source_type), member.source_id, bundle.scope.world_id,
                member.source_digest, datetime.fromisoformat(member.occurred_at) if member.occurred_at else unit.occurred_at,
                member.text, True, True, True, True, False, thread_id=unit.thread_id,
                actor_world_character_id=member.actor_id, counterpart_world_character_id=member.counterpart_id,
                observation_id=member.observation_id, source_event_id=member.source_event_id)
    return sources
