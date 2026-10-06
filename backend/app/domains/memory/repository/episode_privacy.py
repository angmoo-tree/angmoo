"""Current canonical access is the intersection of every admitted input."""
import json

from app.domains.memory.contracts.activity_batch import ACTIVITY_POLICY_VERSION
from app.domains.memory.contracts.provenance import MemorySourceTypeV1
from app.domains.memory.models.activity_configuration import MemoryEpisodeRestriction
from app.domains.memory.models.episode import MemoryEpisodeInfo
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.policies.retrievability import item_retrievable as _item_retrievable
from app.domains.memory.service.items import memory_evidence_blocked_code


def currently_accessible(session, reader, scope, item, now, *, ancestors=frozenset()):
    info = session.get(MemoryEpisodeInfo, item.id)
    if info is None or info.policy_version != ACTIVITY_POLICY_VERSION:
        return True
    if item.id in ancestors or not _item_retrievable(item, now):
        return False
    row = session.get(MemoryEpisodeRestriction, item.id)
    if row is None or row.thread_id != item.thread_id or row.mode not in {"public", "private_thread"}:
        return False
    if (row.mode == "private_thread") != (row.thread_id is not None):
        return False
    try:
        sources, priors = json.loads(row.sources_json), json.loads(row.priors_json)
        if not sources:
            return False
        for source in sources:
            kind = MemorySourceTypeV1(source["type"])
            current = reader.read_evidence(scope=scope, source_type=kind, source_id=source["id"])
            if (current is None or memory_evidence_blocked_code(scope=scope, source_type=kind,
                source_id=source["id"], evidence=current) or current.source_digest != source["digest"]
                or (current.thread_id is not None and current.thread_id != row.thread_id)):
                return False
        for ref in priors:
            prior = session.get(MemoryItem, ref["id"])
            if (prior is None or prior.version != ref["version"]
                or (prior.owner_id, prior.world_id, prior.subject_world_character_id)
                != (scope.owner_id, scope.world_id, scope.subject_world_character_id)
                or not _item_retrievable(prior, now)
                or (prior.thread_id is not None and prior.thread_id != row.thread_id)
                or not currently_accessible(session, reader, scope, prior, now, ancestors=ancestors | {item.id})):
                return False
    except (ValueError, KeyError, TypeError, RecursionError):
        return False
    return True


def new_restriction(item_id, bundle, *, thread_id):
    identities = {(m.source_type, m.source_id): m.source_digest
                  for unit in bundle.source_refs().values() for m in unit.members}
    return MemoryEpisodeRestriction(memory_item_id=item_id,
        mode="private_thread" if thread_id else "public", thread_id=thread_id,
        sources_json=json.dumps([{"type": kind, "id": identifier, "digest": digest}
            for (kind, identifier), digest in sorted(identities.items())], separators=(",", ":")),
        priors_json=json.dumps([{"id": p.item_id, "version": p.item_version}
            for p in bundle.prior_episodes], separators=(",", ":")))
