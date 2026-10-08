"""Exercise real SNS effect transactions with local provider output, never an API."""
import asyncio
import json
from dataclasses import asdict
from datetime import UTC, datetime

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from runtime.test_activity_combined_delivery import fixture
from social.test_feed_reaction_intent import _engine
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.repository.situation_admission import snapshot_for
from app.domains.memory.service.scope import MemoryScopeService
from app.domains.memory.policies.situation_output import parse_description
from app.domains.memory.models.activity_situation import MemorySituationReceipt
from app.domains.memory.models.items import MemoryItem
from app.domains.social.models.posts import Post, PostLike
from app.runtime.memory.composition import memory_repository
from app.runtime.autonomous_activity.situation_memory import freeze_social_input


def enabled(db, lane):
    scope = MemoryScope(lane.ctx.user_id, lane.actor.world_id, lane.actor.id)
    service = MemoryScopeService(memory_repository(db))
    setting = service.get_or_create(scope)
    service.update(scope, expected_version=setting.version, enabled=True, retention_days=180)
    db.commit()
    return snapshot_for(db, scope, locale="ko-KR")


@pytest.mark.parametrize("action,invalid,fail_insert", [
    ("like", False, False), ("comment", False, False),
    ("comment", True, False), ("comment", False, True), ("like", False, True)])
def test_feed_actual_effect_and_receipt_commit_rollback_and_replay(action, invalid, fail_insert):
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            lane, state, _, post = fixture(db)
            snapshot = enabled(db, lane)
            state.update(await lane.load(state))
            state.update(generation_mode="combined", selections=[{"target_id": post.id}], decision_input_receipt={})
            payload = {"selected_targets": state["candidates"], "context": {}}
            manifest = freeze_social_input(lane.ctx, snapshot, node="FeedDecisionDraft", payload=payload,
                transmitted=json.dumps(payload, default=str), state=state)
            state["decision"] = {"decisions": [{"target_id": post.id, "action": action,
                "brief": "응원", "interaction_intent": "ordinary_comment" if action == "comment" else None,
                "comment_purpose": "empathy" if action == "comment" else None}],
                "provisional_draft": {"replies": [{"target_id": post.id, "body": "오늘도 좋은 하루 보내세요."}] if action == "comment" else []},
                "_situation_manifest": manifest.to_dict(),
                "_situations": {post.id: asdict(parse_description(None if invalid else "일상 이야기에 공감했다.", target_key=post.id))}}
            state.update(await lane.validate(state))
            state.update(await lane.write(state))
            before = db.scalar(select(func.count()).select_from(Post))
            db.commit()
            def fail(_connection, _cursor, sql, _params, _context, _many):
                if sql.startswith("INSERT INTO memory_situation_receipts"):
                    raise RuntimeError("injected_receipt_failure")
            if fail_insert:
                event.listen(db.bind, "before_cursor_execute", fail)
            try:
                if fail_insert:
                    with pytest.raises(RuntimeError, match="injected_receipt_failure"):
                        await lane.execute(state)
                else:
                    result = await lane.execute(state)
                    assert result["executions"][0]["status"] == "succeeded"
                    assert (await lane.execute(state))["executions"][0]["status"] == "reused"
            finally:
                if fail_insert:
                    event.remove(db.bind, "before_cursor_execute", fail)
            receipts = list(db.scalars(select(MemorySituationReceipt)))
            assert len(receipts) == (0 if fail_insert else 1)
            assert db.scalar(select(func.count()).select_from(MemoryItem)) == 0
            if receipts:
                assert receipts[0].state == ("blocked" if invalid else "pending"), receipts[0].error_code
            assert db.scalar(select(func.count()).select_from(Post)) == before + (int(action == "comment" and not fail_insert))
            assert db.scalar(select(func.count()).select_from(PostLike)) == int(action == "like" and not fail_insert)
    asyncio.run(scenario())


@pytest.mark.parametrize("fail_insert", [False, True])
def test_inbox_three_real_effects_are_target_scoped_and_receipt_failure_rolls_back(fail_insert):
    from types import SimpleNamespace
    from app.runtime.social.planned_actions import _execute_planned_action
    from app.runtime.autonomous_activity.situation_memory import participant
    with Session(_engine(), expire_on_commit=False) as db:
        lane, state, _, post = fixture(db)
        snapshot = enabled(db, lane)
        targets = [post]
        for number in range(2):
            other = Post(id=f"inbox-situation-{number}", world_id=post.world_id,
                author_world_character_id=post.author_world_character_id, author_character_id=post.author_character_id,
                author_name=post.author_name, title="오늘의 소식", body=f"평범한 일상 {number}", created_at=post.created_at)
            db.add(other); targets.append(other)
        db.commit()
        projections = [{"target_id": p.id, "source_ids": [p.id], "text": p.body} for p in targets]
        payload = {"selected_targets": projections, "context": {}}
        manifest = freeze_social_input(lane.ctx, snapshot, node="InboxDecisionDraft", payload=payload,
            transmitted=json.dumps(payload), state=state)
        state.update(candidates=projections, lane_data={p.id: {"post_id": p.id} for p in targets},
            decision={"decisions": [{"target_id": p.id, "action": "like"} for p in targets],
                "provisional_draft": {"replies": []}, "_situation_manifest": manifest.to_dict(),
                "_situations": {p.id: asdict(parse_description("친구의 안부에 공감했다.", target_key=p.id)) for p in targets}})
        def fail(_connection, _cursor, sql, _params, _context, _many):
            if sql.startswith("INSERT INTO memory_situation_receipts"):
                raise RuntimeError("injected_receipt_failure")
        if fail_insert:
            event.listen(db.bind, "before_cursor_execute", fail)
        try:
            for i, p in enumerate(targets):
                callback = participant(SimpleNamespace(lane="inbox"), state, p.id)
                result = _execute_planned_action(lane.ctx, action={"action_type": "like", "post_id": p.id},
                    scope="inbox", index=i, writing={}, situation_admission=callback)
                assert result["status"] == ("failed" if fail_insert else "succeeded"), result
        finally:
            if fail_insert:
                event.remove(db.bind, "before_cursor_execute", fail)
        receipts = list(db.scalars(select(MemorySituationReceipt)))
        assert len(receipts) == (0 if fail_insert else 3)
        assert {r.target_key for r in receipts} == (set() if fail_insert else {p.id for p in targets})
        assert all(r.state == "pending" for r in receipts)
        assert db.scalar(select(func.count()).select_from(PostLike)) == (0 if fail_insert else 3)


def test_inbox_reply_to_reply_delivery_and_prepared_relationship_are_saved_without_feed_claims():
    from types import SimpleNamespace
    from app.domains.social.models.feed import WorldCharacterFeedObservation
    from app.domains.relationships.models.social import RelationshipState
    from app.domains.relationships.contracts.graph_recall import GraphRecallScope
    from app.domains.relationships.contracts.social_context import RelationshipValidationBinding
    from app.domains.relationships.service.graph_recall import GraphRecallService
    from app.domains.relationships.service.social_context import SocialContextService
    from app.domains.relationships.policies.social_context_validation import receipt_for_snapshot
    from app.runtime.graph_projection.relationship_graph_read import SqlAlchemyRelationshipGraphReadGateway
    from app.runtime.social.planned_actions import _execute_planned_action
    from app.runtime.autonomous_activity.situation_memory import participant
    from app.domains.memory.repository.situation_runs import get_or_create_settings, request_run, claim_run
    from app.domains.memory.repository.situation_apply import apply_page
    from app.domains.memory.repository.situation_validation import restore_context
    from app.runtime.memory.situation_sources import SituationSources
    with Session(_engine(), expire_on_commit=False) as db:
        lane, state, _, reply = fixture(db)
        snapshot = enabled(db, lane)
        now = datetime.now(UTC)
        root = Post(id="inbox-own-root", world_id=reply.world_id, author_world_character_id=lane.actor.id,
            author_character_id=lane.ctx.character.id, author_name=lane.ctx.character.name,
            title="오늘의 하루", body="책을 읽으며 조용히 하루를 보냈다.", created_at=reply.created_at)
        db.add(root); db.flush()
        reply.reply_to_post_id = root.id
        reply.body = "네 이야기를 읽으니 마음이 편안해졌어."
        relation = RelationshipState(id="inbox-prepared-relation", world_id=reply.world_id,
            actor_world_character_id=lane.actor.id, target_world_character_id=reply.author_world_character_id,
            version=6, interaction_count=1, last_metric_at=now)
        db.add(relation); db.commit()
        graph_scope = GraphRecallScope(snapshot.scope.owner_id, reply.world_id, lane.actor.id)
        recall = GraphRecallService(SqlAlchemyRelationshipGraphReadGateway(db))
        social = SocialContextService(lambda query: recall.execute(query, graph_projection_enabled=False)).prepare(
            graph_scope, labels={reply.author_world_character_id: "친구"}, counterpart_id=reply.author_world_character_id, now=now)
        assert len(social.items) == 1
        receipt = receipt_for_snapshot(social, scope=graph_scope, binding=RelationshipValidationBinding(
            lane.ctx.run_id, "inbox", reply.id, reply.author_world_character_id))
        projection = {"target_id": reply.id, "source_ids": [reply.id], "text": reply.body,
            "counterpart_id": reply.author_world_character_id,
            "source_revisions": {reply.id: "fixture", root.id: "fixture"}, "parent_text": root.body,
            "relationship": social.prompt_view()}
        state["relationship_validation_receipts"] = {reply.id: receipt.to_dict()}
        payload = {"selected_targets": [projection], "context": {}}
        # The later canonical value must not replace the prepared facts.
        relation.version = 7; db.commit()
        manifest = freeze_social_input(lane.ctx, snapshot, node="InboxDecisionDraft", payload=payload,
            transmitted=json.dumps(payload, ensure_ascii=False), state=state)
        assert next(source for source in manifest.sources if source.source_type == "RELATIONSHIP").relationship_basis.version == 6
        body = "고마워. 네 말 덕분에 오늘이 더 따뜻해졌어."
        state.update(candidates=[projection], lane_data={reply.id: {"post_id": reply.id}}, decision={
            "decisions": [{"target_id": reply.id, "action": "comment"}],
            "provisional_draft": {"replies": [{"target_id": reply.id, "body": body}]},
            "_situation_manifest": manifest.to_dict(),
            "_situations": {reply.id: asdict(parse_description("내 일상에 남긴 친구의 답글을 읽고 고마움을 전했다.", target_key=reply.id))}})
        result = _execute_planned_action(lane.ctx, action={"action_type": "reply", "post_id": reply.id},
            scope="inbox", index=0, writing={"reply_bodies": [{"scope": "inbox", "index": 0, "post_id": reply.id, "body": body}]},
            situation_admission=participant(SimpleNamespace(lane="inbox"), state, reply.id))
        assert result["status"] == "succeeded", result
        admitted = db.scalar(select(MemorySituationReceipt))
        assert admitted.state == "pending"
        memory = memory_repository(db)
        setting = MemoryScopeService(memory).get_or_create(snapshot.scope)
        get_or_create_settings(db, setting.id, timezone="Asia/Seoul", now=now)
        run = request_run(db, setting, trigger="manual", request_key="inbox-proof-save-001", expected_version=1, now=now)
        token = claim_run(db, run.run_id, now=now); db.commit()
        apply_page(db, memory, SituationSources(db), run_id=run.run_id, token=token, now=now); db.commit()
        assert admitted.state == "applied", admitted.error_code
        restored = restore_context(db, admitted)
        source = next(source for source in restored.sources if source.source_id == reply.id)
        access = SituationSources(db).validate(restored, source, now=now)
        assert access.proof_origin == "situation_delivered" and access.evidence.observation_id is None
        assert db.scalar(select(func.count()).select_from(WorldCharacterFeedObservation)) == 0


@pytest.mark.parametrize("fail_insert", [False, True])
def test_routine_real_post_transaction_and_receipt_replay(monkeypatch, fail_insert):
    from types import SimpleNamespace
    from routine_posts.test_runtime import _engine as routine_engine, _seed, _resident_context, _utc, FakeRoutineProvider
    from app.config import settings
    from app.runtime.routine_posts.sqlalchemy_runtime import prepare_routine_activity, publish_routine_activity
    from app.runtime.autonomous_activity.situation_memory import participant
    from app.domains.memory.contracts.activity_situation import DeliveredInputManifest, stable_digest
    monkeypatch.setattr(settings, "DAILY_PREPARATION_ENABLED", False)
    with Session(routine_engine(), expire_on_commit=False) as db:
        seeded = _seed(db)
        ctx = _resident_context(db, seeded, run_id="routine-situation", now=_utc(datetime(2026, 8, 10, 10, 5)))
        lane = SimpleNamespace(ctx=ctx, actor=seeded.world_character, lane="routine")
        snapshot = enabled(db, lane)
        prepared = prepare_routine_activity(ctx)
        assert not isinstance(prepared, dict), prepared
        generation = asyncio.run(FakeRoutineProvider().generate(resident_context=ctx, routine_context=prepared.context,
            beat=prepared.beat, tracker=prepared.tracker))
        manifest = DeliveredInputManifest("routine-call", snapshot, stable_digest("fixture"), ())
        state = {"identity": {"activity_id": ctx.run_id}, "decision": {
            "provisional_draft": generation.draft.model_dump(), "_situation_manifest": manifest.to_dict(),
            "_situations": {"routine-post": asdict(parse_description("아침 활동을 하고 그 소식을 남겼다.", target_key="routine-post"))}}}
        def fail(_connection, _cursor, sql, _params, _context, _many):
            if sql.startswith("INSERT INTO memory_situation_receipts"):
                raise RuntimeError("injected_receipt_failure")
        db.commit()
        before = db.scalar(select(func.count()).select_from(Post))
        if fail_insert:
            event.listen(db.bind, "before_cursor_execute", fail)
        try:
            result = publish_routine_activity(ctx, prepared=prepared, generation=generation,
                situation_admission=participant(lane, state, "routine-post"))
        finally:
            if fail_insert:
                event.remove(db.bind, "before_cursor_execute", fail)
        assert result["status"] == ("failed" if fail_insert else "completed"), result
        if not fail_insert:
            assert publish_routine_activity(ctx, prepared=prepared, generation=generation,
                situation_admission=participant(lane, state, "routine-post"))["routine_outcome"] == "REUSED_SUCCESS"
        rows = list(db.scalars(select(MemorySituationReceipt)))
        assert len(rows) == (0 if fail_insert else 1)
        assert all(r.state == "pending" for r in rows)
        assert db.scalar(select(func.count()).select_from(Post)) == before + int(not fail_insert)
