"""Compose one admitted job into scoped immutable source bundles."""

from collections import defaultdict
from dataclasses import replace
from datetime import UTC
from hashlib import sha256

from sqlalchemy import select

from app.domains.memory.contracts.episode import EpisodeSourceMember, EpisodeSourceUnit
from app.domains.memory.exceptions import MemoryConflictError, MemoryValidationError
from app.domains.memory.models.batch import MemorySourceDelivery
from app.domains.memory.policies.episode_bundles import partition_episode_units
from app.domains.memory.policies.episode_prompt import episode_prompt_payload
from app.domains.memory.policies.episode_ranges import split_source_unit
from app.domains.memory.repository.episode_candidates import SqlAlchemyEpisodeCandidates
from app.domains.memory.service.items import memory_evidence_blocked_code
from app.runtime.memory.episode_chat_sources import read_episode_chat_page
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
from app.runtime.memory.episode_labels import episode_actor_labels
from app.runtime.memory.episode_social_sources import build_episode_social_sources


def build_episode_job_inputs(session, batch, *, now, prior_search=None):
    scope = batch.setting.scope
    identities = tuple((c.source_type.value, c.source_id) for c in batch.candidates)
    details = RuntimeEpisodeDetailReader(session).read_sources(scope=scope, identities=identities)
    deliveries = session.scalars(select(MemorySourceDelivery).where(
        MemorySourceDelivery.scope_setting_id == batch.setting.id,
        MemorySourceDelivery.batch_job_id == batch.job_id,
        MemorySourceDelivery.candidate_id.in_([c.id for c in batch.candidates]))).all()
    epochs = {row.epoch_id for row in deliveries}
    if len(epochs) != 1 or {row.candidate_id for row in deliveries} != {c.id for c in batch.candidates}:
        raise MemoryConflictError("episode_job_epoch_invalid")
    epoch = next(iter(epochs))
    cutoff = max(batch.cutoff_sequence, *(row.sequence for row in deliveries))
    for candidate in batch.candidates:
        detail = details.get((candidate.source_type.value, candidate.source_id))
        if (detail is None or detail.evidence.source_digest != candidate.source_digest
            or memory_evidence_blocked_code(scope=scope, source_type=candidate.source_type,
                source_id=candidate.source_id, evidence=detail.evidence)):
            raise MemoryConflictError("episode_job_source_changed")
    groups, context = defaultdict(list), {}
    threads = defaultdict(list)
    social = []
    for identity in identities:
        evidence = details[identity].evidence
        if evidence.thread_id:
            threads[evidence.thread_id].append(identity)
        else:
            social.append(identity)
    labels = episode_actor_labels(session, scope=scope,
        actor_ids=(detail.evidence.actor_world_character_id for detail in details.values()))
    for thread, ids in threads.items():
        assistant_ids = tuple(int(identifier) for kind, identifier in ids if kind == "CHAT_MESSAGE" and identifier.isdigit())
        page = read_episode_chat_page(session, scope=scope, thread_id=thread, cutoff=max(assistant_ids, default=0),
            after=min(assistant_ids, default=1) - 1, assistant_ids=assistant_ids)
        groups[thread].extend(page.new_units)
        context[thread] = page.context_units
        paired = {(m.source_type, m.source_id) for unit in page.new_units for m in unit.members}
        for identity in ids:
            if identity in paired:
                continue
            # Older messages can lack a durable request/response association.
            # Keep only that verified source as partial; never guess its pair.
            detail = details[identity]
            evidence = detail.evidence
            occurred = evidence.source_created_at
            occurred = occurred.replace(tzinfo=UTC) if occurred.tzinfo is None else occurred
            member = EpisodeSourceMember(*identity, evidence.source_digest, "unpaired_legacy_message", detail.text,
                total_characters=len(detail.text), actor_label=labels.get(evidence.actor_world_character_id), occurred_at=occurred.isoformat())
            groups[thread].append(EpisodeSourceUnit(f"unpaired:{identity[0]}:{identity[1]}",
                sha256(f"unpaired:{evidence.source_digest}".encode()).hexdigest(), scope, "chat_turn", occurred,
                (member,), thread_id=thread, coverage="partial_source"))
    if social:
        values = build_episode_social_sources(session, scope=scope, identities=tuple(social))
        if values.rejected:
            raise MemoryConflictError("episode_job_source_changed")
        for value in values.inputs:
            groups[value.group_key].append(value.unit)
    result = []
    candidate_reader = SqlAlchemyEpisodeCandidates(session)
    for group, units in groups.items():
        def ordering(unit):
            sequence = max((int(m.source_id) for m in unit.members if m.source_type == "CHAT_MESSAGE" and m.source_id.isdigit()), default=0)
            return (sequence, unit.occurred_at, unit.unit_key) if unit.kind == "chat_turn" else (0, unit.occurred_at, unit.unit_key)
        ordered = tuple(sorted(units, key=ordering))
        ranges = tuple(fragment for unit in ordered for fragment in split_source_unit(unit))
        # A source range is still part of the one candidate; final candidate
        # acceptance waits until all leaves of this immutable plan complete.
        parts = partition_episode_units(ranges, previous_context=context.get(group, ()),
            activation_epoch=epoch, cutoff_sequence=cutoff)
        for part in parts:
            priors = candidate_reader.priors(scope=scope, now=now, thread_id=part.new_units[0].thread_id,
                source_identities=tuple(dict.fromkeys((m.source_type, m.source_id) for u in part.new_units for m in u.members))[:100],
                ranked_fts_ids=() if prior_search is None else prior_search(part))
            while True:
                current = replace(part, bundle_ref=f"B{len(result) + 1}", prior_episodes=priors)
                try:
                    episode_prompt_payload(current)
                    break
                except MemoryValidationError as error:
                    if str(error) != "episode_input_budget_exceeded":
                        raise
                    if not priors:
                        raise
                    priors = priors[:-1]
            result.append(current)
    return tuple(result)
