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
    # Reject a cycle before consulting a completed result. Shared prior memories
    # form a DAG: rechecking the same subtree on each path is exponential work.
    if item.id in ancestors:
        return False
    validation = validation if validation is not None else MemoryAccessValidation(session, now)
    validation.check_context(session, now)
    key = (scope, item.id, item.version)
    if key in validation.completed:
        validation.memo_hits += 1
        return validation.completed[key]
    allowed = _currently_accessible(session, reader, scope, item, now,
        ancestors=ancestors, validation=validation)
    validation.completed[key] = allowed
    return allowed


def _currently_accessible(session, reader, scope, item, now, *, ancestors, validation):
    from app.domains.memory.repository.situation_reads import situation_origin, situation_accessible
    try:
        situation = situation_origin(session, item, validation=validation)
    except ValueError:
        return False
    if situation is not None:
        return situation_accessible(session, reader, scope, item, situation, now,
            ancestors=ancestors, validation=validation)
    info = validation.get(MemoryEpisodeInfo, item.id)
    if info is None or info.policy_version == "episode-selection.v1":
        return True
    if info.policy_version != ACTIVITY_POLICY_VERSION:
        return False
    if item.id in ancestors or not _item_retrievable(item, now):
        return False
    row = validation.get(MemoryEpisodeRestriction, item.id)
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
            key = scope, kind.value, source["id"]
            if key not in validation.evidence:
                validation.evidence[key] = reader.read_evidence(scope=scope, source_type=kind, source_id=source["id"])
            current = validation.evidence[key]
            if (current is None or memory_evidence_blocked_code(scope=scope, source_type=kind,
                source_id=source["id"], evidence=current) or current.source_digest != source["digest"]
                or (current.thread_id is not None and current.thread_id != row.thread_id)):
                return False
        for ref in priors:
            prior = validation.get(MemoryItem, ref["id"])
            if (prior is None or prior.version != ref["version"]
                or (prior.owner_id, prior.world_id, prior.subject_world_character_id)
                != (scope.owner_id, scope.world_id, scope.subject_world_character_id)
                or not _item_retrievable(prior, now)
                or (prior.thread_id is not None and prior.thread_id != row.thread_id)
                or not currently_accessible(session, reader, scope, prior, now,
                    ancestors=ancestors | {item.id}, validation=validation)):
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
