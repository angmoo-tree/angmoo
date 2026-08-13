from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app import models
from app.cruds import graph_projection as graph_projection_crud


DATABASE_URL = os.getenv("P7_GRAPH_POSTGRES_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="P7_GRAPH_POSTGRES_DATABASE_URL is required",
)


def test_skip_locked_claim_has_one_owner_for_same_outbox() -> None:
    assert DATABASE_URL is not None
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    suffix = uuid4().hex[:12]
    world_id = f"p7-concurrency-world-{suffix}"
    user_id = f"p7-concurrency-user-{suffix}"
    character_id = f"p7-concurrency-character-{suffix}"
    membership_id = f"p7-concurrency-membership-{suffix}"
    world_character_id = f"p7-concurrency-wc-{suffix}"
    event_id = f"p7-concurrency-event-{suffix}"
    outbox_id = f"p7-concurrency-outbox-{suffix}"
    now = datetime.now(UTC)
    with Session(engine) as db:
        user = models.User(
            id=user_id,
            email=f"{suffix}@example.test",
            display_name="P7 Concurrent",
            display_name_normalized=f"p7 concurrent {suffix}",
            privacy_policy_version="test",
            terms_version="test",
            profile_setup_completed=True,
        )
        character = models.Character(
            id=character_id,
            owner_id=user_id,
            name="P7 Concurrent",
            handle=f"p7-concurrent-{suffix}",
            one_liner="A concurrency test resident",
            personality="Calm and precise.",
            speech_style="Concise.",
            worldview="Reliable events build trust.",
            topic_preferences="Testing",
            safety_rules="Stay inside the local fixture.",
            persona_summary="A local P7 concurrency fixture.",
            moderation_status="active",
        )
        world = models.World(
            id=world_id,
            slug=f"p7-concurrent-{suffix}",
            owner_user_id=user_id,
            name="Concurrent World",
            tagline="A test world",
            setting_description="A bounded test world.",
            daily_life_description="Residents test concurrency.",
            genre_tags=["test"],
            tone_tags=["calm"],
            timezone="Asia/Seoul",
            language="ko",
            visibility="private",
            join_policy="invite_only",
            status="draft",
            contract_version="world-v1",
            contract_hash="c" * 64,
            readiness_status="not_ready",
            create_idempotency_key=f"p7-concurrency-create-{suffix}",
        )
        db.add_all([user, character, world])
        db.flush()
        membership = models.WorldMembership(
            id=membership_id,
            world_id=world_id,
            user_id=user_id,
            role="owner",
            status="active",
            joined_at=now,
        )
        db.add(membership)
        db.flush()
        wc = models.WorldCharacter(
            id=world_character_id,
            world_id=world_id,
            character_id=character_id,
            membership_id=membership_id,
            status="active",
            character_contract_hash="d" * 64,
            world_contract_hash=world.contract_hash,
        )
        db.add(wc)
        db.flush()
        event = models.SocialEvent(
            id=event_id,
            world_id=world_id,
            actor_world_character_id=world_character_id,
            target_world_character_id=None,
            event_type="post_published",
            result="succeeded",
            occurred_at=now,
            idempotency_key=f"p7-concurrency-event-key-{suffix}",
            schema_version="social-event-v1",
            retrieval_status="eligible",
        )
        db.add(event)
        db.flush()
        db.add(
            models.GraphProjectionOutbox(
                id=outbox_id,
                world_id=world_id,
                source_event_id=event_id,
                projection_type="social_event",
                payload_version="relationship-v1",
                payload={
                    "world_id": world_id,
                    "source_event_id": event_id,
                    "actor_world_character_id": world_character_id,
                    "target_world_character_id": None,
                },
                source_signature="0" * 64,
                dedupe_key=f"p7-concurrency-dedupe-{suffix}",
                status="pending",
                attempt_count=0,
                created_at=datetime(2020, 1, 1, tzinfo=UTC),
                updated_at=datetime(2020, 1, 1, tzinfo=UTC),
            )
        )
        db.commit()

    def claim(worker_id: str) -> list[str]:
        with Session(engine) as db:
            rows = graph_projection_crud.claim_batch(
                db,
                worker_id=worker_id,
                now=now,
                batch_size=1,
            )
            db.commit()
            return rows

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(claim, ["worker-a", "worker-b"]))
        assert sum(outbox_id in result for result in results) == 1
        with Session(engine) as db:
            row = db.get(models.GraphProjectionOutbox, outbox_id)
            assert row is not None
            assert row.status == "processing"
            assert row.attempt_count == 1
    finally:
        with Session(engine) as db:
            db.execute(delete(models.GraphProjectionOutbox).where(models.GraphProjectionOutbox.id == outbox_id))
            db.execute(delete(models.SocialEvent).where(models.SocialEvent.id == event_id))
            db.execute(delete(models.WorldCharacter).where(models.WorldCharacter.id == world_character_id))
            db.execute(delete(models.WorldMembership).where(models.WorldMembership.id == membership_id))
            db.execute(delete(models.World).where(models.World.id == world_id))
            db.execute(delete(models.Character).where(models.Character.id == character_id))
            db.execute(delete(models.User).where(models.User.id == user_id))
            db.commit()
