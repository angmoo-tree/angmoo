"""Current canonical access is the intersection of every admitted input."""
import json

from app.domains.memory.contracts.access_validation import MemoryAccessValidation
from app.domains.memory.contracts.activity_batch import ACTIVITY_POLICY_VERSION
from app.domains.memory.contracts.provenance import MemorySourceTypeV1
from app.domains.memory.models.activity_configuration import MemoryEpisodeRestriction
from app.domains.memory.models.episode import MemoryEpisodeInfo
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.policies.retrievability import item_retrievable as _item_retrievable
from app.domains.memory.service.items import memory_evidence_blocked_code


def currently_accessible(session, reader, scope, item, now, *, ancestors=frozenset(), validation=None):
    """Current memory rights; source edits/deletions do not revoke an experience."""
    from app.domains.memory.repository.experience import accessible
    validation = validation if validation is not None else MemoryAccessValidation(session, now)
    validation.check_context(session, now)
    key = (scope, item.id, item.version)
    if key in validation.completed:
        validation.memo_hits += 1
        return validation.completed[key]
    allowed = accessible(session, scope, item, now, validation=validation, reader=reader)
    validation.completed[key] = allowed
    return allowed

def new_restriction(item_id, bundle, *, thread_id):
    identities = {(m.source_type, m.source_id): m.source_digest
                  for unit in bundle.source_refs().values() for m in unit.members}
    return MemoryEpisodeRestriction(memory_item_id=item_id,
        mode="private_thread" if thread_id else "public", thread_id=thread_id,
        sources_json=json.dumps([{"type": kind, "id": identifier, "digest": digest}
            for (kind, identifier), digest in sorted(identities.items())], separators=(",", ":")),
        priors_json=json.dumps([{"id": p.item_id, "version": p.item_version}
            for p in bundle.prior_episodes], separators=(",", ":")))
