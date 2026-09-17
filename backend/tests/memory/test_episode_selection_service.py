import asyncio
from dataclasses import replace

from sqlalchemy import select, func

from app.domains.memory.contracts.episode import EpisodeSelection, EpisodeProposal
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.repository.episode_work import SqlAlchemyEpisodeWork
from app.domains.memory.service.episode_selection import EpisodeSelectionService
from memory.test_episode_apply import preparation
from memory.test_episode_packet_repository import Details
from memory.test_p8_l_g_memory_write_lifecycle import memory_session, NOW


class Provider:
    def __init__(self, *, split=False, during=None):
        self.calls, self.split, self.during = 0, split, during
    def validate_bundle(self, bundle):
        pass
    async def select(self, bundle, *, timeout):
        self.calls += 1
        if self.during:
            self.during()
        if self.split:
            return EpisodeSelection((), (), needs_split=True)
        return EpisodeSelection((EpisodeProposal("약속 후 취소 소식을 들었다.", tuple(f"S{i}" for i in range(1, len(bundle.new_units) + 1))),), ())


def start(db):
    applier, setting, bundle, values = preparation(db)
    works = SqlAlchemyEpisodeWork(db)
    work, = works.plan(job_id="episode-job", setting=setting, bundles=(bundle,), candidate_ids=(), now=NOW, job_fence=lambda: None)
    db.commit()
    service = EpisodeSelectionService(works=works, applier=applier, detail_reader=Details(values),
        revalidate=lambda _: values, commit=db.commit, rollback=db.rollback, clock=lambda: NOW)
    return service, works, work, setting, values


def execute(service, work, setting, provider):
    return asyncio.run(service.run_work(work=work, setting=setting, provider=provider, model_id="model",
        thinking_level="high", profile_version=1, timeout=10, job_fence=lambda: None))


def test_one_call_completed_and_repeated_work_does_not_call_again(memory_session):
    service, works, work, setting, values = start(memory_session)
    provider = Provider()
    assert execute(service, work, setting, provider) == "episode_selection_completed"
    completed, = works.list(job_id="episode-job", setting=setting)
    assert execute(service, completed, setting, provider) == "episode_work_already_processed"
    assert provider.calls == 1
    assert memory_session.scalar(select(func.count(MemoryItem.id))) == 1


def test_provider_split_creates_bounded_children_without_parent_memory(memory_session):
    service, works, work, setting, values = start(memory_session)
    assert execute(service, work, setting, Provider(split=True)) == "episode_needs_split"
    planned = works.list(job_id="episode-job", setting=setting)
    assert len(planned) == 3
    assert planned[0].state == "split"
    assert [len(value.manifest["new"]) for value in planned[1:]] == [1, 1]
    assert memory_session.scalar(select(func.count(MemoryItem.id))) == 0
    for child in planned[1:]:
        assert execute(service, child, setting, Provider()) == "episode_selection_completed"
    assert memory_session.scalar(select(func.count(MemoryItem.id))) == 2


def test_changed_original_during_call_leaves_no_memory_and_retains_attempt(memory_session):
    service, works, work, setting, values = start(memory_session)
    def change():
        values[("POST", "0")] = replace(values[("POST", "0")], source_digest="f" * 64)
    assert execute(service, work, setting, Provider(during=change)) == "episode_apply_source_changed"
    pending, = works.list(job_id="episode-job", setting=setting)
    assert pending.calls == 1
    assert pending.state == "pending"
    assert memory_session.scalar(select(func.count(MemoryItem.id))) == 0
