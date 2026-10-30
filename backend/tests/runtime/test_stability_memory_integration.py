"""One frozen SNS decision: commit, restart, later action, memory and evidence.

Only synthetic SQLite sources are used. There is no provider client.
"""
import asyncio
from dataclasses import asdict, replace
from datetime import UTC, datetime
import json

from sqlalchemy import select
from runtime.test_activity_relationship_validation import relation_case, _lane
from runtime.test_relationship_effect_progress import state_for
from memory.test_activity_situation_receipt import enabled
from app.runtime.social.planned_actions import _execute_planned_action
from app.runtime.autonomous_activity.situation_memory import freeze_social_input
from app.runtime.memory.composition import memory_repository
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.policies.situation_output import parse_description
from app.domains.memory.models.activity_situation import MemorySituationReceipt, MemorySituationApplyRun
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.service.scope import MemoryScopeService
from app.domains.memory.repository.situation_runs import get_or_create_settings, request_run, claim_run
from app.domains.memory.repository.situation_apply import apply_page
from app.domains.memory.repository.recall import SqlAlchemyMemoryRecallDocumentSource
from app.runtime.memory.situation_application_sources import PreparedSituationSources
from app.runtime.memory.source_composition import source_evidence_reader
from app.runtime.memory.sqlite_fts5_recall import SqliteMemoryRecallIndex, MemoryRecallIndexSettings
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.domains.memory.contracts.recall import MemoryRecallSearchQuery, RecallDocumentKind
from app.domains.chat.service.evidence_assembly import EvidenceBundleAssembler
from app.domains.chat.contracts.evidence_display import validate_projection
from app.domains.chat.contracts.today_sns_activity import TodaySnsActivityEntry
from model_fixture_support import models


def test_restart_same_decision_applies_each_effect_and_memory_once(relation_case, tmp_path):
    case = relation_case
    db = case.db
    lane, state = state_for(case)
    snapshot = replace(enabled(db, lane), memory_search_locale="en-US")
    sources = []
    for candidate in state["candidates"]:
        post = db.get(models.Post, candidate["target_id"])
        sources.append({"target_id": post.id, "source_ids": [post.id], "text": post.body})
        candidate.update(source_ids=[post.id],text=post.body)
    from app.runtime.memory.captured_delivery import post_reference, bind_candidate_sources
    from app.runtime.autonomous_activity.initial_input import seal
    references={row['target_id']:post_reference(db.get(models.Post,row['target_id'])) for row in sources}
    bind_candidate_sources(state['candidates'],references)
    state['lane_data']['_reference_sources']=references
    state.update(seal(state,{}))
    payload = {"selected_targets": sources, "context": {}}
    manifest = freeze_social_input(lane.ctx, snapshot, node="InboxDecisionDraft", payload=payload,
        transmitted=json.dumps(payload), state=state)
    description = "Ian acknowledged the author's earlier afternoon note with a like."
    state["decision"].update(_situation_manifest=manifest.to_dict(), _situations={
        source["target_id"]: asdict(parse_description(description, target_key=source["target_id"], locale="en-US")) for source in sources})
    # JSON boundary represents persisted immutable provider output, never rerun.
    state = json.loads(json.dumps(state))
    lane.action_executor = _execute_planned_action
    # Preserve the original full decision digest even though execution stops
    # immediately after the first commit.
    original = lane.action_executor
    def first_then_interrupt(*args, **kwargs):
        if kwargs["index"] == 1:
            raise InterruptedError("synthetic stop after first commit")
        return original(*args, **kwargs)
    lane.action_executor = first_then_interrupt
    try:
        asyncio.run(lane.execute(state))
    except InterruptedError:
        pass
    assert len(list(db.scalars(select(models.PostLike)))) == 1
    restarted = _lane(case); restarted.lane = "inbox"; restarted.action_executor = original
    result = asyncio.run(restarted.execute(state))
    assert [row["status"] for row in result["executions"]] == ["reused", "succeeded"]
    assert all(row["status"] == "reused" for row in asyncio.run(restarted.execute(state))["executions"])
    receipts = list(db.scalars(select(MemorySituationReceipt)))
    assert len(receipts) == 2 and all(row.description == description for row in receipts)
    scope = MemoryScope(lane.ctx.user_id, lane.actor.world_id, lane.actor.id)
    setting = MemoryScopeService(memory_repository(db)).get_or_create(scope)
    now = datetime.now(UTC)
    get_or_create_settings(db, setting.id, timezone="UTC", now=now)
    request = request_run(db, setting, trigger="manual", request_key="synthetic-integration-apply", expected_version=1, now=now)
    for _ in receipts:
        token = claim_run(db, request.run_id, now=now); db.commit()
        apply_page(db, memory_repository(db), PreparedSituationSources(db), run_id=request.run_id, token=token, now=now); db.commit()
    assert db.get(MemorySituationApplyRun, request.run_id).state == "completed"
    assert all(row.state == "applied" for row in receipts), [(row.state, row.error_code) for row in receipts]
    documents = {}
    for row in receipts:
        item = db.get(MemoryItem, row.applied_item_id)
        documents[item.id] = SqlAlchemyMemoryRecallDocumentSource._documents_for_item(session=db,
            reader=source_evidence_reader(db), item=item, evidences=[], now=now, episode_only=True)
        assert documents[item.id][0].text == description
    index = SqliteMemoryRecallIndex(StaticRuntimeDataPath(tmp_path / "recall"), settings=MemoryRecallIndexSettings(generation="memory-episode-v1"))
    index.open()
    try:
        index.replace_memory_items(documents)
        hits = index.search(MemoryRecallSearchQuery(scope, "afternoon note", (RecallDocumentKind.MEMORY_ITEM,), 5))
        assert {hit.memory_item_id for hit in hits} == set(documents)
    finally:
        index.close()
    source = db.get(models.Post, sources[0]["target_id"])
    entry = TodaySnsActivityEntry(opaque_reference="today:synthetic", kind="reactions_given", event_type="like_added",
        source_type="post", source_id=source.id, source_revision="a"*64, occurred_at=now, actor_label="Ian", counterpart_label="Author",
        content_mode="full", title=source.title, body=source.body, parent_title=None, parent_body=None,
        root_title=None, root_body=None, root_post_id=None, source_post_id=source.id, target_post_id=source.id,
        content_complete=True, truncated=False, subjective_context=None)
    evidence = EvidenceBundleAssembler._today_item(entry)
    assert validate_projection(evidence.display_projection, evidence.opaque_reference, evidence.text)
    assert len(list(db.scalars(select(models.PostLike)))) == len(receipts) == len(documents) == 2
