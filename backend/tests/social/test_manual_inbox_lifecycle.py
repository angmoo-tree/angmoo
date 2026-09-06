from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from model_fixture_support import models
from app.domains.social.contracts.inbox import ManualInboxRuntimeError
from app.runtime.social.manual_inbox import manual_inbox_service, source_id
from routine_posts.test_runtime import _engine, _seed
from relationships.test_social_event_runtime import _character


def test_manual_inbox_claim_is_durable_consume_rolls_back_and_rejection_commits():
    engine = _engine()
    now = datetime(2026, 8, 10, 2, 0, tzinfo=UTC)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        actor = _character(fixture.user, "manual-lifecycle")
        db.add(actor)
        db.flush()
        owner = models.WorldCharacter(
            id="manual-lifecycle-owner",
            world_id=fixture.world.id,
            character_id=actor.id,
            membership_id=fixture.world_character.membership_id,
            role_key="student",
            status="active",
            control_mode="owner_controlled",
            owner_user_id=fixture.user.id,
            autonomous_enabled=False,
            activity_runtime_mode="legacy_resident_v1",
            feed_runtime_mode="legacy_latest_v1",
            local_profile={},
            character_contract_hash="a" * 64,
            world_contract_hash=fixture.world.contract_hash,
        )
        db.add(owner)
        db.flush()
        target = models.Post(
            id="manual-lifecycle-target",
            author_name="Target",
            title="Target",
            body="A public question",
            author_character_id=fixture.character.id,
            world_id=fixture.world.id,
            author_world_character_id=fixture.world_character.id,
            activity_episode_id=fixture.morning_episode.id,
        )
        db.add(target)
        db.flush()
        reply = models.Post(
            id="manual-lifecycle-reply",
            author_name="Owner",
            title="Reply",
            body="A direct answer",
            author_character_id=actor.id,
            world_id=fixture.world.id,
            author_world_character_id=owner.id,
            reply_to_post_id=target.id,
        )
        beat = models.ActivityBeat(
            id="manual-lifecycle-beat",
            world_id=fixture.world.id,
            world_character_id=fixture.world_character.id,
            episode_id=fixture.morning_episode.id,
            sequence_no=1,
            scheduled_for=now,
            trigger_kind="scheduled",
            status="pending",
            idempotency_key="manual-lifecycle-beat",
        )
        db.add_all([reply, beat])
        db.flush()
        row = models.OwnerManualInboxCandidate(
            id="manual-lifecycle-candidate",
            world_id=fixture.world.id,
            actor_world_character_id=owner.id,
            target_world_character_id=fixture.world_character.id,
            source_reply_post_id=reply.id,
            target_post_id=target.id,
            created_at=now,
        )
        db.add(row)
        db.commit()
        commits = []
        event.listen(db, "after_commit", lambda *_: commits.append("commit"))
        candidate_args = dict(
            world_id=fixture.world.id,
            consumer_world_character_id=fixture.world_character.id,
            episode_id=fixture.morning_episode.id,
            after=now - timedelta(seconds=1),
            before=now,
        )
        found = manual_inbox_service.candidates(db, **candidate_args)
        assert [item.source_event_id for item in found] == [source_id(row.id)]
        assert found[0].episode_relevance == 100
        assert commits == []
        claim_args = dict(
            source_event_id=source_id(row.id),
            world_id=fixture.world.id,
            consumer_world_character_id=fixture.world_character.id,
            target_activity_beat_id=beat.id,
            claim_run_id="first-run",
            claim_expires_at=now + timedelta(minutes=5),
            now=now,
        )
        assert manual_inbox_service.claim(db, **claim_args) is row
        assert row.status == "claimed"
        assert commits == ["commit"]
        with pytest.raises(ManualInboxRuntimeError, match="already_claimed"):
            manual_inbox_service.claim(
                db, **{**claim_args, "claim_run_id": "other-run"}
            )
        assert commits == ["commit"]
        with pytest.raises(ManualInboxRuntimeError, match="claim_mismatch"):
            manual_inbox_service.consume_claims(
                db,
                source_event_ids=[source_id(row.id)],
                target_activity_beat_id=beat.id,
                claim_run_id="other-run",
                now=now,
            )
        version = row.version
        manual_inbox_service.consume_claims(
            db,
            source_event_ids=[source_id(row.id)],
            target_activity_beat_id=beat.id,
            claim_run_id="first-run",
            now=now,
        )
        assert row.status == "consumed"
        assert row.version == version + 1
        assert commits == ["commit"]
        db.rollback()
        assert row.status == "claimed"
        assert row.claim_run_id == "first-run"
        assert row.version == version
        manual_inbox_service.release_claims(
            db, source_event_ids=[source_id(row.id)], claim_run_id="first-run"
        )
        assert row.status == "released"
        assert row.claim_run_id is None
        assert commits == ["commit", "commit"]
        db.add(
            models.WorldCharacterBlock(
                id="manual-lifecycle-block",
                world_id=fixture.world.id,
                blocker_world_character_id=fixture.world_character.id,
                blocked_world_character_id=owner.id,
            )
        )
        assert manual_inbox_service.candidates(db, **candidate_args) == []
        assert row.status == "rejected"
        assert row.rejected_reason_code == "source_context_invalid"
        assert commits == ["commit", "commit", "commit"]
        db.rollback()
        assert row.status == "rejected"
        assert db.get(models.WorldCharacterBlock, "manual-lifecycle-block") is not None
    engine.dispose()
