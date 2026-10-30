from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.contracts.activity_thought import parse_activity_thought
from app.domains.chat.models import ChatMessageThought, MessageMessage
from app.domains.chat.repository.response_lifecycle import SqlAlchemyResponseLifecycleRepository
from app.domains.memory.contracts.episode import EpisodeSelection, EpisodeProposal
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.exceptions import MemoryConflictError
from app.domains.memory.policies.episode_bundles import partition_episode_units
from app.domains.memory.policies.episode_packets import bounded_episode_packets
from app.domains.memory.repository.episode_apply import SqlAlchemyEpisodeApply
from app.domains.memory.repository.episode_packets import SqlAlchemyEpisodePackets
from app.runtime.memory.episode_chat_sources import read_episode_chat_page
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
from app.runtime.memory.episode_revalidation import revalidate_episode_bundle
from chat.test_p8_l_j_response_generation_lifecycle import response_session, _ready_to_commit, _commit_payload, _fence
from memory.test_p8_l_g_memory_write_lifecycle import _enabled_service, FakeSourceReader


def setup(db):
    now = datetime.now(UTC)
    lifecycle = SqlAlchemyResponseLifecycleRepository(db)
    record = _ready_to_commit(lifecycle, now)
    payload = replace(_commit_payload(record), activity_thought=parse_activity_thought("前に助けてもらったので、今度は私が助けたい。"))
    done = lifecycle.finalize_response(_fence(record), payload, now=now + timedelta(seconds=1))
    db.commit()
    scope = MemoryScope("response-owner", "response-world", "response-responding")
    _, memory, _ = _enabled_service(db, scope, FakeSourceReader())
    page = read_episode_chat_page(db, scope=scope, thread_id=record.thread_id, cutoff=done.committed_assistant_message_id)
    bundle = partition_episode_units(page.new_units, activation_epoch="test-epoch", cutoff_sequence=1)[0]
    return scope, memory, bundle, done, now + timedelta(seconds=2)


def test_committed_turn_episode_original_and_own_thought_roundtrip(response_session):
    db = response_session
    scope, memory, bundle, done, now = setup(db)
    ids = SqlAlchemyEpisodeApply(db, memory).apply(bundle=bundle,
        selection=EpisodeSelection((EpisodeProposal("사용자와 이야기하며 도움을 주고 싶다고 생각했다.", ("S1",)),), ()),
        setting=memory.get_scope_setting(scope), now=now,
        revalidate=lambda b: revalidate_episode_bundle(db, b), job_fence=lambda: None)
    db.commit()
    packets = SqlAlchemyEpisodePackets(db, detail_reader=RuntimeEpisodeDetailReader(db)).read(scope=scope, item_ids=ids, now=now)
    assert len(packets) == 1
    assert len(packets[0].units) == 1
    assert len(packets[0].units[0].sources) == 2
    assert packets[0].units[0].thought.text == bundle.new_units[0].thought.text
    assert all(source.status == "verified" for source in packets[0].units[0].sources)
    delivery = bounded_episode_packets(packets)
    assert "前に助けてもらった" in delivery.text
    assert delivery.packets[0]["partial"] is False


@pytest.mark.parametrize("changed", ["thought", "original", "range"])
def test_captured_chat_survives_later_changes_but_stored_input_tampering_fails(response_session, changed):
    db = response_session
    scope, memory, bundle, done, now = setup(db)
    from app.domains.memory.service.episode_manifest import episode_input_manifest,restore_episode_input
    manifest=episode_input_manifest(bundle)
    if changed == "thought":
        db.get(ChatMessageThought, done.committed_assistant_message_id).thought_text = "뒤늦게 변경된 생각"
    elif changed == "original":
        db.get(MessageMessage, done.committed_assistant_message_id).content = "수정된 원문"
    else:
        manifest['new'][0]['members'][0]['text']='가짜'
        manifest['new'][0]['members'][0]['characters']=2
        with pytest.raises(MemoryConflictError,match='episode_manifest_revision_changed'):
            restore_episode_input(manifest,scope=scope,detail_reader=None)
        return
    db.flush()
    restored=restore_episode_input(manifest,scope=scope,detail_reader=None)
    ids=SqlAlchemyEpisodeApply(db, memory).apply(bundle=restored,
        selection=EpisodeSelection((EpisodeProposal("당시 대화를 기억한다.", ("S1",)),), ()),
        setting=memory.get_scope_setting(scope), now=now,
        revalidate=lambda b: revalidate_episode_bundle(db, b), job_fence=lambda: None)
    packet=SqlAlchemyEpisodePackets(db,detail_reader=None).read(scope=scope,item_ids=ids,now=now)[0]
    assert [s.text for u in packet.units for s in u.sources]==[m.text for u in bundle.new_units for m in u.members]
    assert packet.units[0].thought==bundle.new_units[0].thought
