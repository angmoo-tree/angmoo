"""One-time, restart-safe refresh of derived vector authorization metadata.

Canonical memories and stored vectors are unchanged. Existing vector payloads
are reused by the normal worker when their summary/profile hash still matches.
"""
from sqlalchemy import inspect, text
from app.core.sqlite_concurrency import run_sqlite_session_immediate


def refresh_policy(projection):
    with projection._factory() as db:
        if not inspect(db.get_bind()).has_table("memory_experience_snapshots"):
            return False
        marker = "experience:projection:" + projection.generation
        def refresh():
            if db.execute(text("SELECT revision FROM memory_vector_validation_revisions WHERE scope_key=:key"),
                    {"key":marker}).scalar_one_or_none():
                return False
            # Source dependencies belong to the discarded live-source policy.
            # Current scope/deletion rights are re-established by owned snapshots.
            db.execute(text("DELETE FROM memory_vector_dependencies"))
            db.execute(text("""INSERT INTO memory_vector_work
                (generation,item_id,world_id,desired_revision,applied_revision,last_change,state,due_at,lease_until)
                SELECT :generation,e.memory_item_id,m.world_id,1,0,0,'pending',0,0
                FROM memory_vector_eligibility e JOIN memory_items m ON m.id=e.memory_item_id
                WHERE true ON CONFLICT(generation,item_id) DO UPDATE SET
                desired_revision=memory_vector_work.desired_revision+1,state='pending',due_at=0,
                claim_token=NULL,lease_until=0,last_code=NULL"""),{"generation":projection.generation})
            db.execute(text("INSERT INTO memory_vector_validation_revisions(scope_key,revision) VALUES (:key,1)"),{"key":marker})
            return True
        return run_sqlite_session_immediate(db, refresh, require_clean=True)
