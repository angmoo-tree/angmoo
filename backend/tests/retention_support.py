"""Synthetic file-backed canonical/checkpoint fixtures; never use account keys."""
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.domains.world_characters.activity_models import ActivityGraphRun
from app.domains.world_characters.contracts.checkpoint_retention import CheckpointRetention, RETENTION_KEY
from app.domains.world_characters.models import CharacterActiveWorld, WorldCharacter
from app.domains.world_characters.service.activity_engines import bind_run
from app.models import Base
from social.test_feed_reaction_intent import _seed

NOW = datetime(2026, 10, 2, 12, tzinfo=UTC)


def database(root: Path, *, seed=True):
    root.mkdir(parents=True, exist_ok=True)
    path = root / "canonical-test.sqlite3"
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False, "timeout": .05})

    @event.listens_for(engine, "connect")
    def configure(raw, _record):
        raw.execute("PRAGMA foreign_keys=ON")

    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    if not seed:
        return engine, factory, None
    with factory() as db:
        ctx, post = _seed(db, with_candidate=True)
        actor = db.get(WorldCharacter, db.get(CharacterActiveWorld, ctx.character.id).world_character_id)
        run = bind_run(db, actor=actor, activity_id=ctx.run_id)
        db.commit()
        identifiers = (ctx.user_id, ctx.character.id, actor.id, actor.world_id, post.id)
    return engine, factory, identifiers


def result(*, version=2, count=0):
    return {"engine": "personalized_graph_v2", "contract_version": version,
        "status": "completed" if count else "observed", "summary": "Synthetic completed activity",
        "execution_order": ["inbox", "feed", "routine"] if version == 2 else ["inbox", "routine", "feed"],
        "publish_result": {"public_action_count": count},
        "paths": {key: {"path": key, "status": "completed" if key == "feed" and count else "no_action",
            "public_action_count": count if key == "feed" else 0} for key in ("inbox", "feed", "routine")},
        "llm_usage_summary": {"calls": 0}, "llm_rate_limit_waits": [],
        "recovery_reservations": [], "routine_policy": {"preserved": True}}


def completed(db, identifiers, *, identifier="old", age=timedelta(days=2), marked=True,
              status="observed", confirmed=True):
    _, _, actor_id, world_id, _ = identifiers
    payload = result(count=1 if status == "completed" else 0)
    if marked:
        payload[RETENTION_KEY] = CheckpointRetention(graph_complete=confirmed).model_dump()
    row = ActivityGraphRun(activity_id=identifier, world_character_id=actor_id,
        world_id=world_id, engine="personalized_graph_v2", contract_version=2,
        status=status, stage="Finalize", started_at=NOW - age - timedelta(minutes=1),
        finished_at=NOW - age, result=payload)
    db.add(row)
    db.commit()
    return row


async def checkpoint(saver, identifier, *, namespace="", blob=b"detail", step=0):
    from langgraph.checkpoint.base import empty_checkpoint
    value = empty_checkpoint()
    value["channel_values"] = {"detail": blob}
    value["channel_versions"] = {"detail": str(step + 1)}
    config = {"configurable": {"thread_id": "activity:" + identifier, "checkpoint_ns": namespace}}
    saved = await saver.aput(config, value, {"source": "input", "step": step, "parents": {}}, {"detail": str(step + 1)})
    await saver.aput_writes(saved, [("detail", blob)], "fixture-task")
    return saved
