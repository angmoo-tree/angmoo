from dataclasses import replace
from datetime import timedelta

from app.domains.memory.contracts.episode import EpisodeSelection, EpisodeProposal
from app.domains.memory.models.episode import MemoryEpisodeLink
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.repository.episode_candidates import SqlAlchemyEpisodeCandidates
from memory.test_episode_apply import preparation
from memory.test_p8_l_g_memory_write_lifecycle import memory_session, NOW


def test_distant_next_day_change_links_prior_outside_overlap(memory_session):
    from app.domains.memory.contracts.episode import EpisodePriorCandidate
    db = memory_session
    apply, setting, bundle, values = preparation(db)
    initial = replace(bundle, new_units=bundle.new_units[:1])
    first, = apply.apply(bundle=initial,
        selection=EpisodeSelection((EpisodeProposal("연습을 돕겠다고 제안했다.", ("S1",)),), ()),
        setting=setting, now=NOW, revalidate=lambda _: {("POST", "0"): values[("POST", "0")]}, job_fence=lambda: None)
    db.commit()
    # A new day/turn 120 is not in the preceding five-source window.
    later = NOW + timedelta(days=1)
    original = bundle.new_units[1]
    following = replace(bundle, bundle_ref="B120", new_units=(replace(original, unit_key="turn-120", occurred_at=later),),
        context_units=(), cutoff_sequence=120,
        prior_episodes=SqlAlchemyEpisodeCandidates(db).priors(scope=setting.scope, now=later, ranked_fts_ids=(first,)))
    assert following.prior_episodes[0].item_id == first
    second, = apply.apply(bundle=following,
        selection=EpisodeSelection((EpisodeProposal("다음 날 연습 취소 소식을 들었다.", ("S1",), ("P1",)),), ()),
        setting=setting, now=later, revalidate=lambda _: {("POST", "1"): values[("POST", "1")]}, job_fence=lambda: None)
    db.commit()
    assert SqlAlchemyEpisodeCandidates(db).followups(scope=setting.scope, item_ids=(first,), now=later).item_ids == (first, second)
    assert db.get(MemoryItem, first).summary == "연습을 돕겠다고 제안했다."


def create(db, count=4):
    apply, setting, bundle, values = preparation(db)
    ids = apply.apply(bundle=bundle, selection=EpisodeSelection(tuple(
        EpisodeProposal(f"연습 {i}번째 상태", ("S1", "S2")) for i in range(count)), ()),
        setting=setting, now=NOW, revalidate=lambda _: values, job_fence=lambda: None)
    db.commit()
    return setting, ids


def test_prior_candidates_bounded_and_recheck_untrusted_hits(memory_session):
    db = memory_session
    setting, ids = create(db, 12)
    repo = SqlAlchemyEpisodeCandidates(db)
    # Exact links precede lexical or recent candidates; one source can belong
    # to several legitimate situations, without creating a new provider call.
    values = repo.priors(scope=setting.scope, now=NOW, source_identities=(("POST", "0"),), ranked_fts_ids=("foreign",))
    assert len(values) == 8
    assert all(row.item_id in ids for row in values)
    assert repo.priors(scope=replace(setting.scope, owner_id="other"), now=NOW, ranked_fts_ids=ids) == ()
    db.get(MemoryItem, ids[0]).valid_until = NOW - timedelta(seconds=1)
    # Move valid_from back as well to keep the DB validity constraint valid.
    db.get(MemoryItem, ids[0]).valid_from = NOW - timedelta(days=2)
    db.flush()
    values = repo.priors(scope=setting.scope, now=NOW, ranked_fts_ids=(ids[0], ids[1]))
    assert values[0].item_id == ids[1]
    assert ids[0] not in {row.item_id for row in values}


def test_followup_chain_reads_cancel_without_replacing_history_and_stops_cycles(memory_session):
    db = memory_session
    setting, ids = create(db)
    for old, new in zip(ids, ids[1:]):
        db.add(MemoryEpisodeLink(prior_item_id=old, following_item_id=new, created_at=NOW))
    db.add(MemoryEpisodeLink(prior_item_id=ids[-1], following_item_id=ids[0], created_at=NOW))
    db.flush()
    repo = SqlAlchemyEpisodeCandidates(db)
    result = repo.followups(scope=setting.scope, item_ids=(ids[0],), now=NOW)
    assert result.item_ids == ids
    assert not result.truncated
    limited = repo.followups(scope=setting.scope, item_ids=(ids[0],), now=NOW, limit=2)
    assert limited.item_ids == ids[:2]
    assert limited.truncated
    assert repo.followups(scope=replace(setting.scope, owner_id="other"), item_ids=ids, now=NOW).item_ids == ()


def test_deleted_following_episode_is_not_presented_as_current_update(memory_session):
    db = memory_session
    setting, ids = create(db, 2)
    db.add(MemoryEpisodeLink(prior_item_id=ids[0], following_item_id=ids[1], created_at=NOW))
    row = db.get(MemoryItem, ids[1])
    row.status, row.deleted_at = "deleted", NOW
    db.flush()
    result = SqlAlchemyEpisodeCandidates(db).followups(scope=setting.scope, item_ids=(ids[0],), now=NOW)
    assert result.item_ids == ids[:1]
