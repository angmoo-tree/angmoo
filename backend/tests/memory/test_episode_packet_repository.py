from dataclasses import replace

import pytest
from sqlalchemy.exc import OperationalError

from app.domains.memory.contracts.episode import EpisodeSelection, EpisodeProposal
from app.domains.memory.contracts.episode_packet import EpisodeSourceDetail
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.repository.episode_packets import SqlAlchemyEpisodePackets
from memory.test_episode_apply import preparation
from memory.test_p8_l_g_memory_write_lifecycle import memory_session, NOW


class Details:
    def __init__(self, values):
        self.values = values
        self.calls = []

    def read_sources(self, *, scope, identities):
        self.calls.append(identities)
        return {key: EpisodeSourceDetail(value, "원문", "verified-author") for key, value in self.values.items() if key in identities}

    def read_thoughts(self, *, scope, references):
        return {}


def test_episode_snapshot_keeps_captured_sources_after_originals_disappear(memory_session):
    apply, setting, bundle, values = preparation(memory_session)
    ids = apply.apply(bundle=bundle,
        selection=EpisodeSelection((EpisodeProposal("취소 소식에 위로했다.", ("S1", "S2")),), ()),
        setting=setting, now=NOW, revalidate=lambda _: values, job_fence=lambda: None)
    memory_session.commit()
    reader = Details(values)
    repo = SqlAlchemyEpisodePackets(memory_session, detail_reader=reader)
    complete = repo.read(scope=setting.scope, item_ids=ids, now=NOW)
    assert reader.calls == []
    assert all(s.status == "verified" for u in complete[0].units for s in u.sources)
    assert all(s.author_id is None for u in complete[0].units for s in u.sources)  # Uncaptured author is not invented later.
    reader.values = {("POST", "0"): values[("POST", "0")]}
    partial = repo.read(scope=setting.scope, item_ids=ids, now=NOW)
    assert len(partial) == 1
    assert partial[0].summary == complete[0].summary
    assert [s.status for u in partial[0].units for s in u.sources] == ["verified", "verified"]
    reader.values = {}
    missing = repo.read(scope=setting.scope, item_ids=ids, now=NOW)
    assert len(missing) == 1
    assert all(s.text == "원문" for u in missing[0].units for s in u.sources)
    assert all(s.author_id is None for u in missing[0].units for s in u.sources)
    calls = len(reader.calls)
    assert repo.read(scope=MemoryScope("other", setting.scope.world_id, setting.scope.subject_world_character_id), item_ids=ids, now=NOW) == ()
    assert len(reader.calls) == calls


def test_live_source_reader_is_never_called_but_snapshot_database_errors_propagate(memory_session, monkeypatch):
    apply, setting, bundle, values = preparation(memory_session)
    ids = apply.apply(bundle=bundle, selection=EpisodeSelection((EpisodeProposal("경험", ("S1", "S2")),), ()),
        setting=setting, now=NOW, revalidate=lambda _: values, job_fence=lambda: None)
    reader = Details({key: replace(value, source_digest="c" * 64) for key, value in values.items()})
    repo = SqlAlchemyEpisodePackets(memory_session, detail_reader=reader)
    result = repo.read(scope=setting.scope, item_ids=ids, now=NOW)
    assert all(s.status == "verified" for u in result[0].units for s in u.sources)
    assert all(s.author_id is None for u in result[0].units for s in u.sources)
    def failed(**kwargs):
        raise OperationalError("read failed", {}, None)
    reader.read_sources = failed
    assert repo.read(scope=setting.scope, item_ids=ids, now=NOW) == result
    from app.domains.memory.repository import experience
    def unavailable(*args, **kwargs):
        raise OperationalError("snapshot read failed", {}, None)
    monkeypatch.setattr(experience, "read_snapshot", unavailable)
    with pytest.raises(OperationalError):
        repo.read(scope=setting.scope, item_ids=ids, now=NOW)
