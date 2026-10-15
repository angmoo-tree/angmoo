"""Persist a received review without repeating its provider call."""
from datetime import UTC, datetime
from app.core.sqlite_concurrency import run_sqlite_session_immediate
from app.domains.relationships.contracts.daily_review import manifest_digest, validate_review_result
from app.domains.relationships.models.personalization import RelationshipReviewWork


def persist_received(sessions, work_id, record, references_factory):
    from app.domains.relationships.service.daily_review import _root, _payload
    with sessions() as db:
        def apply():
            row = db.get(RelationshipReviewWork, work_id, populate_existing=True)
            if row is None:
                return "lease_lost"
            if row.status in {"ready", "applied", "stale"}:
                return row.status
            if (row.status != "running" or (row.lease_token, row.attempts, row.manifest_digest) !=
                (record["lease"], record["attempt"], record["manifest_digest"])):
                return "lease_lost"
            root = _root(db, row)
            if root.manifest_digest != record["root_digest"]:
                return "lease_lost"
            references_factory(db).revalidate(root)
            payload = _payload(db, row)
            if payload is None:
                return "lease_lost"
            refs = ({m["memory_id"] for m in payload["memories"]} if "memories" in payload
                else {ref for part in payload["partial_results"] for ref in part["memory_refs"]})
            if record["partial"] != (row.phase in {"partial", "reduce"}) or set(record["allowed_refs"]) != refs:
                raise ValueError("relationship_review_manifest_changed")
            # The current DB writer adopts this exact durable attempt. It never
            # re-labels an older attempt as a newer provider submission.
            result = validate_review_result(record["result"], partial=row.phase in {"partial", "reduce"},
                allowed_refs=refs)
            if manifest_digest(result) != record["result_digest"]:
                raise ValueError("relationship_review_result_changed")
            row.result = {**result, "_execution": {"duration_ms": record["duration_ms"],
                "usage": record.get("usage"), "attempt": row.attempts, "result_digest": record["result_digest"]}}
            row.status, row.lease_token, row.lease_until, row.error_code = "ready", None, None, None
            return "ready"
        return run_sqlite_session_immediate(db, apply, require_clean=True)


def may_publish(sessions, work_id, record, now):
    with sessions() as db:
        row = db.get(RelationshipReviewWork, work_id)
        if row is None or row.lease_until is None:
            return False
        until = row.lease_until.replace(tzinfo=UTC) if row.lease_until.tzinfo is None else row.lease_until
        return (row.status == "running" and until > now and
            (row.lease_token, row.attempts, row.manifest_digest) ==
            (record["lease"], record["attempt"], record["manifest_digest"]))
