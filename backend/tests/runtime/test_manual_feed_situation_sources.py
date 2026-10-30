"""Feed keeps root candidates and canonical comment context separate."""
import asyncio
import json
from dataclasses import asdict
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from model_fixture_support import models
from memory.test_activity_situation_receipt import enabled
from runtime.test_activity_combined_delivery import fixture
from social.test_feed_reaction_intent import _engine
from app.domains.memory.models.activity_situation import MemorySituationReceipt
from app.domains.memory.policies.situation_output import parse_description
from app.domains.memory.repository.situation_validation import restore_context
from app.runtime.autonomous_activity.situation_memory import freeze_social_input
from app.runtime.memory.situation_sources import SituationSources


@pytest.mark.parametrize("action", ["comment", "like", "no_action"])
def test_feed_owner_root_and_comment_context_use_post_reply_without_manual_claim(action, deny_external_network):
    async def scenario():
        with Session(_engine(), expire_on_commit=False) as db:
            lane, state, _, root = fixture(db)
            author = db.get(models.WorldCharacter, root.author_world_character_id)
            author.control_mode, author.owner_user_id = "owner_controlled", root.author_user_id
            author.autonomous_enabled = False
            reply = models.Post(id="owner-feed-comment", world_id=root.world_id, author_name=root.author_name,
                author_user_id=root.author_user_id, author_character_id=root.author_character_id,
                author_world_character_id=author.id, title="", body="The alchemy experiment used a cooler temperature.",
                post_type="reply", reply_to_post_id=root.id, search_document="alchemy research",
                created_at=root.created_at)
            db.add(reply); db.commit()
            snapshot = enabled(db, lane)
            state["identity"].update(world_id=lane.actor.world_id, actor_id=lane.actor.id)
            state.update(await lane.load(state))
            # The index returns both. Actual candidate policy must discard the reply.
            assert [c["target_id"] for c in state["candidates"]] == [root.id]
            state.update(generation_mode="combined", selections=[{"target_id": root.id}], decision_input_receipt={})
            # Canonical context, when provided, uses a real REPLY; it is not a
            # second root candidate or a synthetic manual-inbox identifier.
            from app.runtime.relationships.experience_metrics import post_revision
            payload = {"selected_targets": state["candidates"], "context": {"source_manifest": [
                {"post_id": reply.id, "excerpt": reply.body, "target_ref": author.id,
                 "revision": post_revision(reply), "created_at": reply.created_at.isoformat()}]}}
            from app.runtime.memory.captured_delivery import post_reference
            from app.runtime.autonomous_activity.initial_input import seal
            state["lane_data"]["_reference_sources"][reply.id] = post_reference(reply)
            state["decision_context"] = payload["context"]
            state.update(seal(state, {}))
            manifest = freeze_social_input(lane.ctx, snapshot, node="FeedDecisionDraft", payload=payload,
                transmitted=json.dumps(payload, default=str), state=state)
            assert {(s.source_type, s.source_id) for s in manifest.sources} == {("POST", root.id), ("REPLY", reply.id)}
            assert db.scalar(select(func.count()).select_from(models.OwnerManualInboxCandidate)) == 0
            state["decision"] = {"decisions": [{"target_id": root.id, "action": action, "brief": "Acknowledge the experiment.",
                "interaction_intent": "ordinary_comment" if action == "comment" else None,
                "comment_purpose": "empathy" if action == "comment" else None}],
                "provisional_draft": {"replies": [{"target_id": root.id, "body": "That is a useful experiment."}] if action == "comment" else []},
                "_situation_manifest": manifest.to_dict(),
                "_situations": {root.id: asdict(parse_description("I considered the experiment and its comment.", target_key=root.id))}}
            state.update(await lane.validate(state))
            state.update(await lane.write(state))
            before = db.scalar(select(func.count()).select_from(models.Post))
            db.commit()
            result = await lane.execute(state)
            assert result["executions"][0]["status"] == ("no_action" if action == "no_action" else "succeeded")
            assert db.scalar(select(func.count()).select_from(models.Post)) == before + (action == "comment")
            assert db.scalar(select(func.count()).select_from(models.PostLike)) == (action == "like")
            receipts = list(db.scalars(select(MemorySituationReceipt)))
            assert len(receipts) == (action != "no_action")
            if receipts:
                context = restore_context(db, receipts[0])
                source = next(s for s in context.sources if s.source_type == "REPLY")
                from app.domains.memory.repository.experience import validate_captured_sources
                assert next(access for entry, access in validate_captured_sources(db, context, (), receipts[0],
                    now=datetime.now(UTC)) if entry == source).state == "available"
                reply.report_hidden_at = datetime.now(UTC)
                db.commit(); db.expire_all()
                assert SituationSources(db).validate(context, source, now=datetime.now(UTC)).state != "available"
    asyncio.run(scenario())
