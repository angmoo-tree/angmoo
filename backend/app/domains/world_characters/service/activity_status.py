"""Owner-scoped inspection of effective engine, current state and recent progress."""
from sqlalchemy import select

from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.activity_models import ActivityEnginePolicy, ActivityGraphRun
from app.domains.world_characters.service.activity_engines import resolve_engine
from app.domains.world_characters.service.activity_state import read_state, utc


def owned_actor(db, *, actor_id, world_id, owner_id, read_character):
    actor = db.get(WorldCharacter, actor_id)
    character = read_character(db, actor.character_id) if actor else None
    if actor is None or actor.world_id != world_id or character is None or character.deleted_at:
        raise LookupError("activity_actor_not_found")
    if character.owner_id != owner_id:
        raise PermissionError("activity_actor_not_owned")
    return actor


def activity_status(db, *, actor):
    policies = {}
    for scope, key in (("character", f"character:{actor.id}"), ("world", f"world:{actor.world_id}"), ("global", "global")):
        row = db.get(ActivityEnginePolicy, key)
        policies[scope] = {"engine": row.engine if row else None, "version": row.version if row else 0}
    runs = list(db.scalars(select(ActivityGraphRun).where(ActivityGraphRun.world_character_id == actor.id,
        ActivityGraphRun.world_id == actor.world_id).order_by(ActivityGraphRun.started_at.desc()).limit(5)))
    return {"world_id": actor.world_id, "world_character_id": actor.id,
        "autonomous_enabled": actor.autonomous_enabled, "control_mode": actor.control_mode,
        "effective": resolve_engine(db, actor), "policies": policies,
        "current_state": read_state(db, world_id=actor.world_id, actor_id=actor.id),
        "runs": [{"activity_id": r.activity_id, "engine": r.engine, "status": r.status,
            "stage": r.stage, "started_at": utc(r.started_at), "finished_at": utc(r.finished_at),
            "paths": {name: {"status": path.get("status"), "public_action_count": path.get("public_action_count", 0),
                "selected_count": len(path.get("selected_ids", [])), "recall_count": len(path.get("recall_status", {})),
                "reason": path.get("reason") or (path.get("failure") or {}).get("reason")}
                for name, path in (r.result or {}).get("paths", {}).items()},
            "public_action_count": (r.result or {}).get("publish_result", {}).get("public_action_count"),
            "reason": (r.result or {}).get("reason")} for r in runs]}
