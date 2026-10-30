"""The released SQLite 0.1.3 input, independent of PostgreSQL-only controls."""
from sqlalchemy import text

CONTROL_TABLES = frozenset({"memory_situation_runs", "relationship_review_requests", "relationship_review_work"})


def metadata():
    from app.runtime.persistence.model_registration import register_models
    from app.runtime.persistence.sqlite_schema import build_sqlite_baseline_metadata
    register_models()
    return build_sqlite_baseline_metadata()


def additional_values(table, source):
    """Preserve failure evidence and require explicit recovery of old failures."""
    if table not in CONTROL_TABLES:
        return {}
    control = {}
    status = source.get("status", source.get("state"))
    if status in {"failed", "partial_failed", "needs_attention", "blocked", "error"}:
        control = {"hold": "manual", "migration_reason": "legacy_failure", "revision": 0}
    if table in {"memory_situation_runs", "relationship_review_work"} and status == "running":
        control = {"hold":"manual","migration_reason":"legacy_inflight_requires_recovery","revision":0,
            "source_state":status,"source_lease_token":source.get("lease_token"),
            "source_lease_until":str(source.get("lease_until")) if source.get("lease_until") is not None else None}
    return {"maintenance": control}


def source_values(table, source):
    result=dict(source)
    status=source.get('status',source.get('state'))
    if table in {"memory_situation_runs", "relationship_review_work"} and status=='running':
        result['status' if table=='relationship_review_work' else 'state']='failed' if table=='relationship_review_work' else 'error'
        for key in ('lease_token','lease_until'):
            if key in result:result[key]=None
        if 'error_code' in result:result['error_code']='migration_recovery_required'
    return result


def verify_target_only(connection):
    if connection.execute(text("SELECT count(*) FROM memory_maintenance_slot WHERE token IS NOT NULL OR owner IS NOT NULL")).scalar_one():
        raise ValueError("migration_live_maintenance_owner")
    for name in CONTROL_TABLES:
        if connection.execute(text(f"SELECT count(*) FROM {name} WHERE maintenance IS NULL OR jsonb_typeof(maintenance) <> 'object'")).scalar_one():
            raise ValueError("migration_maintenance_control_invalid")
