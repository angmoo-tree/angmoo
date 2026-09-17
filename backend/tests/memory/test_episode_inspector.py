import json

from app.domains.chat.models import MessageMessage
from app.domains.memory.contracts.episode import EpisodeProposal, EpisodeSelection
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.memory.repository.episode_apply import SqlAlchemyEpisodeApply
from app.domains.memory.repository.episode_packets import SqlAlchemyEpisodePackets
from app.domains.memory.policies.episode_packets import bounded_episode_packets
from app.domains.memory.policies.episode_provider_view import episode_provider_view
from app.domains.memory.schemas import EpisodeDetailRead
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
from app.runtime.memory.episode_inspector import episode_detail_view, episode_receipt_view
from app.runtime.memory.episode_revalidation import revalidate_episode_bundle
from app.runtime.memory.episode_sns import sns_episode_text
from memory.test_episode_chat_pipeline import setup, response_session


def prepare(db):
    scope, memory, bundle, done, now = setup(db)
    ids = SqlAlchemyEpisodeApply(db, memory).apply(bundle=bundle,
        selection=EpisodeSelection((EpisodeProposal("도움을 주고 싶었던 경험", ("S1",)),), ()),
        setting=memory.get_scope_setting(scope), now=now,
        revalidate=lambda b: revalidate_episode_bundle(db, b), job_fence=lambda: None)
    db.commit()
    packet = SqlAlchemyEpisodePackets(db, detail_reader=RuntimeEpisodeDetailReader(db)).read(scope=scope, item_ids=ids, now=now)
    receipt = json.dumps(bounded_episode_packets(episode_provider_view(packet)).packets[0], ensure_ascii=False)
    return scope, ids[0], done, now, receipt


def test_detail_owner_off_and_receipt_only_revalidates_delivered_material(response_session):
    db = response_session
    scope, item_id, done, now, receipt = prepare(db)
    view = episode_detail_view(db, scope, item_id, now)
    EpisodeDetailRead.model_validate(view)
    assert view["units"][0]["thought"]["status"] == "recorded"
    summary, visible = episode_receipt_view(db, scope, item_id, now, receipt)
    assert not visible["partial"]
    from sqlalchemy import select
    db.scalar(select(MemoryScopeSettingModel).where(MemoryScopeSettingModel.owner_id == scope.owner_id)).enabled = False
    db.flush()
    assert episode_detail_view(db, scope, item_id, now) is not None
    db.get(MessageMessage, done.committed_assistant_message_id).content = "나중에 수정된 답변"
    db.flush()
    summary, changed = episode_receipt_view(db, scope, item_id, now, receipt)
    assert changed["partial"]
    assert any(s["status"] == "changed" for u in changed["units"] for s in u["sources"])
    assert "나중에 수정된 답변" not in json.dumps(changed, ensure_ascii=False)
    assert changed["units"][0]["thought"]["status"] == "invalid"


def test_public_sns_never_uses_private_chat_episode(response_session):
    db = response_session
    scope, item_id, done, now, receipt = prepare(db)
    assert sns_episode_text(db, scope=scope, now=now) == ""
