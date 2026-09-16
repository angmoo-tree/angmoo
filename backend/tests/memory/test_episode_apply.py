from dataclasses import replace

import pytest
from sqlalchemy import func, select

from app.domains.memory.contracts.episode import EpisodeBundle, EpisodeSourceUnit, EpisodeSourceMember, EpisodeSelection, EpisodeProposal
from app.domains.memory.models.episode import MemoryEpisodeBundle, MemoryEpisodeInfo, MemoryEpisodeProcessedUnit, MemoryEpisodeUnitEvidence
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.models.embedding import MemoryVectorEligibility
from app.domains.memory.repository.episode_apply import SqlAlchemyEpisodeApply
from app.domains.memory.exceptions import MemoryConflictError
from memory.test_p8_l_g_memory_write_lifecycle import memory_session, _seed_world, _enabled_service, FakeSourceReader, _evidence, NOW


def preparation(db):
    scope, _ = _seed_world(db)
    _, memory, _ = _enabled_service(db, scope, FakeSourceReader())
    setting = memory.get_scope_setting(scope)
    values = {("POST", str(i)): _evidence(scope=scope, source_id=str(i)) for i in range(2)}
    units = tuple(EpisodeSourceUnit(
        unit_key=f"post:{i}", unit_revision=values[("POST", str(i))].source_digest,
        scope=scope, kind="sns_interaction", occurred_at=NOW,
        members=(EpisodeSourceMember("POST", str(i), values[("POST", str(i))].source_digest, "self", "원문"),),
    ) for i in range(2))
    bundle = EpisodeBundle("B1", scope, units, activation_epoch="test-epoch", cutoff_sequence=2)
    return SqlAlchemyEpisodeApply(db, memory), setting, bundle, values


def test_multiple_episodes_share_source_without_raw_copy_and_replay_once(memory_session):
    db = memory_session
    apply, setting, bundle, values = preparation(db)
    selection = EpisodeSelection((EpisodeProposal("함께 연습했다.", ("S1", "S2")), EpisodeProposal("격려를 나눴다.", ("S2",))), ())
    args = dict(bundle=bundle, selection=selection, setting=setting, now=NOW, revalidate=lambda _: values, job_fence=lambda: None)
    ids = apply.apply(**args)
    db.commit()
    assert len(ids) == 2
    assert apply.apply(**args) == ids
    assert db.scalar(select(func.count(MemoryItem.id))) == 2
    assert db.scalar(select(func.count(MemoryEpisodeProcessedUnit.id))) == 2
    assert db.scalar(select(func.count(MemoryEpisodeUnitEvidence.unit_id))) == 3
    assert db.scalar(select(func.count(MemoryVectorEligibility.memory_item_id))) == 2
    assert "원문" not in db.scalar(select(MemoryEpisodeBundle.manifest_json))
    with pytest.raises(MemoryConflictError, match="result_conflict"):
        apply.apply(**(args | {"selection": EpisodeSelection((EpisodeProposal("다른 정리", ("S1", "S2")),), ())}))


@pytest.mark.parametrize("failure", ["changed", "missing", "fence"])
def test_stale_or_late_result_leaves_no_partial_episode(memory_session, failure):
    db = memory_session
    apply, setting, bundle, values = preparation(db)
    if failure == "changed":
        values[("POST", "1")] = replace(values[("POST", "1")], source_digest="f" * 64)
    if failure == "missing":
        values.pop(("POST", "1"))
    def fence():
        if failure == "fence":
            raise MemoryConflictError("stale_job")
    with pytest.raises(MemoryConflictError):
        apply.apply(bundle=bundle, selection=EpisodeSelection((EpisodeProposal("사건", ("S1",)),), ("S2",)),
                    setting=setting, now=NOW, revalidate=lambda _: values, job_fence=fence)
    assert db.scalar(select(func.count(MemoryItem.id))) == 0
    assert db.scalar(select(func.count(MemoryEpisodeBundle.id))) == 0
    assert db.scalar(select(func.count(MemoryEpisodeProcessedUnit.id))) == 0


def test_zero_episodes_is_a_durable_processed_result(memory_session):
    db = memory_session
    apply, setting, bundle, values = preparation(db)
    assert apply.apply(bundle=bundle, selection=EpisodeSelection((), ("S1", "S2")),
                       setting=setting, now=NOW, revalidate=lambda _: values, job_fence=lambda: None) == ()
    assert db.scalar(select(func.count(MemoryEpisodeInfo.memory_item_id))) == 0
    assert db.scalar(select(func.count(MemoryEpisodeProcessedUnit.id))) == 2
