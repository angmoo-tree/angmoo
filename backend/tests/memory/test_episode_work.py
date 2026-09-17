import json

import pytest
from sqlalchemy import select, func

from app.domains.memory.contracts.episode import EpisodeProposal, EpisodeSelection
from app.domains.memory.exceptions import MemoryConflictError
from app.domains.memory.models.episode import MemoryEpisodeBundle
from app.domains.memory.repository.episode_work import SqlAlchemyEpisodeWork
from memory.test_episode_apply import preparation
from memory.test_p8_l_g_memory_write_lifecycle import memory_session, NOW


def test_durable_attempt_counter_and_application_share_one_receipt(memory_session):
    db = memory_session
    apply, setting, bundle, values = preparation(db)
    repository = SqlAlchemyEpisodeWork(db)
    work, = repository.plan(job_id="episode-job", setting=setting, bundles=(bundle,), candidate_ids=("candidate",),
                            now=NOW, job_fence=lambda: None)
    db.commit()
    assert "원문" not in db.get(MemoryEpisodeBundle, work.id).manifest_json
    number = repository.start_call(work, model_id="model", thinking_level="high", profile_version=1, now=NOW, job_fence=lambda: None)
    db.commit()
    # A fresh repository resumes the same frozen input, not a newly grouped day.
    work, = SqlAlchemyEpisodeWork(db).list(job_id="episode-job", setting=setting)
    assert work.calls == 1 and work.state == "running"
    repository.finish_call(work, call_number=number, code="episode_selection_completed", elapsed_ms=10, job_fence=lambda: None)
    ids = apply.apply(bundle=bundle, selection=EpisodeSelection((EpisodeProposal("경험", ("S1", "S2")),), ()),
        setting=setting, now=NOW, revalidate=lambda _: values, job_fence=lambda: None)
    db.commit()
    assert len(ids) == 1
    assert db.scalar(select(func.count(MemoryEpisodeBundle.id))) == 1
    finished, = repository.list(job_id="episode-job", setting=setting)
    assert finished.state == "completed" and finished.calls == 1
    usage = repository.usage(job_id="episode-job", setting=setting)
    assert usage["logical_attempts"] == 1
    assert usage["unknown_physical_attempts"] == 1
    assert usage["known_physical_calls"] == 0
    assert usage["latency_ms"] == 10
    with pytest.raises(MemoryConflictError, match="attempts_exhausted"):
        repository.start_call(finished, model_id="model", thinking_level="high", profile_version=1, now=NOW, job_fence=lambda: None)


def test_restart_does_not_reset_three_call_budget(memory_session):
    db = memory_session
    _, setting, bundle, _ = preparation(db)
    repository = SqlAlchemyEpisodeWork(db)
    work, = repository.plan(job_id="episode-job", setting=setting, bundles=(bundle,), candidate_ids=(),
                            now=NOW, job_fence=lambda: None)
    db.commit()
    for attempt in range(1, 4):
        repository = SqlAlchemyEpisodeWork(db)
        work, = repository.list(job_id="episode-job", setting=setting)
        assert repository.start_call(work, model_id="model", thinking_level="high", profile_version=1, now=NOW, job_fence=lambda: None) == attempt
        db.commit()
        repository.finish_call(work, call_number=attempt, code="episode_timeout", elapsed_ms=10, job_fence=lambda: None)
        db.commit()
    work, = repository.list(job_id="episode-job", setting=setting)
    assert work.state == "failed" and work.calls == 3
    assert repository.plan(job_id="episode-job", setting=setting, bundles=(bundle,), candidate_ids=(), now=NOW, job_fence=lambda: None) == (work,)
    with pytest.raises(MemoryConflictError):
        repository.start_call(work, model_id="model", thinking_level="high", profile_version=1, now=NOW, job_fence=lambda: None)
