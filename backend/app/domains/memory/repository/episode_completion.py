"""Finish admitted candidates only after every source range was processed."""

from sqlalchemy import select, update

from app.domains.memory.exceptions import MemoryConflictError
from app.domains.memory.models.episode import MemoryEpisodeInfo
from app.domains.memory.models.items import MemoryCandidate, MemoryItemEvidence


def complete_episode_candidates(repository, batch, works, *, now):
    if any(work.state not in {"completed", "split"} for work in works):
        raise MemoryConflictError("episode_work_incomplete")
    repository.fence(batch, now=now)
    db = repository.session
    links = db.execute(select(MemoryItemEvidence.source_type, MemoryItemEvidence.source_id,
        MemoryItemEvidence.memory_item_id).join(MemoryEpisodeInfo,
            MemoryEpisodeInfo.memory_item_id == MemoryItemEvidence.memory_item_id).where(
                MemoryEpisodeInfo.bundle_id.in_([work.id for work in works if work.state == "completed"]))).all()
    retained = {}
    for source_type, source_id, item_id in links:
        retained.setdefault((source_type, source_id), item_id)
    for candidate in batch.candidates:
        item_id = retained.get((candidate.source_type.value, candidate.source_id))
        # Parent/context references are allowed evidence but must not fabricate
        # newly admitted candidates outside this immutable job snapshot.
        changed = db.execute(update(MemoryCandidate).where(MemoryCandidate.id == candidate.id,
            MemoryCandidate.scope_setting_id == batch.setting.id, MemoryCandidate.status == "pending",
            MemoryCandidate.version == candidate.version, MemoryCandidate.source_digest == candidate.source_digest,
        ).values(status="accepted" if item_id else "rejected", decided_at=now, version=candidate.version + 1,
                 reason_code="episode_retained" if item_id else "memory_selection_skipped"))
        if changed.rowcount != 1:
            raise MemoryConflictError("episode_candidate_changed")
        repository.record_decision(batch, candidate, decision="retain" if item_id else "skip",
            reason="episode_retained" if item_id else "memory_selection_skipped", item_id=item_id, now=now)
    repository.complete(batch, now=now)
