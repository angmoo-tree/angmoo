"""Resolve inherited engine policy and freeze it once per activity claim."""
from datetime import UTC, datetime

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.domains.world_characters.activity_models import ActivityEnginePolicy, ActivityGraphRun
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.schemas.activity_state import ActivityEngine

CONTRACT_VERSION = 2
SUPPORTED_CONTRACT_VERSIONS = frozenset({1, 2})
DEFAULT_ACTIVITY_ENGINE: ActivityEngine = "personalized_graph_v2"


def routine_state_version(db: Session, actor: WorldCharacter) -> int:
    from app.config import settings
    from app.contracts.routine_output import select_policy
    engine = resolve_engine(db, actor)["engine"]
    return select_policy(engine=engine, sns_version=2 if engine == "personalized_graph_v2" else 1,
        output_policy=settings.ROUTINE_OUTPUT_POLICY, thought_policy=settings.ACTIVITY_THOUGHT_POLICY).state_schema_version


def resolve_engine(db: Session, actor: WorldCharacter) -> dict:
    for key, source in ((f"character:{actor.id}", "character"), (f"world:{actor.world_id}", "world"), ("global", "global")):
        row = db.get(ActivityEnginePolicy, key, populate_existing=True)
        if row is not None:
            if row.world_id not in (None, actor.world_id) or row.world_character_id not in (None, actor.id):
                raise ValueError("engine_policy_scope_invalid")
            return {"engine": row.engine, "source": source, "version": row.version}
    return {"engine": DEFAULT_ACTIVITY_ENGINE, "source": "default", "version": 0}


def set_engine(db: Session, *, engine: ActivityEngine | None, expected_version: int,
               world_id: str | None = None, actor_id: str | None = None) -> None:
    """Caller authorizes ownership; policy never changes autonomy eligibility."""
    if engine not in (None, "current", "personalized_graph_v2"):
        raise ValueError("engine_invalid")
    if actor_id:
        actor = db.get(WorldCharacter, actor_id)
        if actor is None or actor.world_id != world_id or actor.control_mode != "autonomous":
            raise ValueError("engine_actor_scope_invalid")
    key = f"character:{actor_id}" if actor_id else f"world:{world_id}" if world_id else "global"
    row = db.get(ActivityEnginePolicy, key, populate_existing=True)
    if (row.version if row else 0) != expected_version:
        raise ValueError("engine_policy_conflict")
    if row is None:
        if engine is not None:
            db.add(ActivityEnginePolicy(scope_key=key, world_id=world_id, world_character_id=actor_id,
                engine=engine, version=1, updated_at=datetime.now(UTC)))
    else:
        condition = (ActivityEnginePolicy.scope_key == key, ActivityEnginePolicy.version == expected_version)
        statement = delete(ActivityEnginePolicy).where(*condition) if engine is None else update(ActivityEnginePolicy).where(*condition).values(
            engine=engine, version=expected_version + 1, updated_at=datetime.now(UTC))
        if db.execute(statement).rowcount != 1:
            raise ValueError("engine_policy_conflict")
    db.flush()


def bind_run(db: Session, *, actor: WorldCharacter, activity_id: str) -> ActivityGraphRun:
    """Existing runs keep their engine even if policy changes during execution."""
    row = db.get(ActivityGraphRun, activity_id)
    if row is not None:
        if ((row.world_id, row.world_character_id) != (actor.world_id, actor.id)
                or row.contract_version not in SUPPORTED_CONTRACT_VERSIONS
                or (row.engine == "current" and row.contract_version != 1)):
            raise ValueError("activity_run_scope_or_version_invalid")
        return row
    engine = resolve_engine(db, actor)["engine"]
    from dataclasses import asdict
    from app.config import settings
    from app.contracts.routine_output import select_policy
    policy = select_policy(engine=engine, sns_version=CONTRACT_VERSION if engine == "personalized_graph_v2" else 1,
        output_policy=settings.ROUTINE_OUTPUT_POLICY, thought_policy=settings.ACTIVITY_THOUGHT_POLICY)
    from app.domains.world_characters.service.name_binding import resolve_name_binding
    binding = resolve_name_binding(db, actor=actor, owner_id=actor.owner_user_id)
    row = ActivityGraphRun(activity_id=activity_id, world_id=actor.world_id,
        world_character_id=actor.id, engine=engine,
        contract_version=CONTRACT_VERSION if engine == "personalized_graph_v2" else 1,
        status="running", stage="LoadContext", started_at=datetime.now(UTC),
        result={"routine_policy": asdict(policy), "name_binding_policy": binding.policy_version, "name_binding": binding.to_dict()})
    db.add(row)
    db.flush()
    return row
