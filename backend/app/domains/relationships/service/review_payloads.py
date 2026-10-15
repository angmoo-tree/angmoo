"""Shared frozen review payload operations on the caller-owned transaction."""

from sqlalchemy import select
from app.core.ids import uuid7_string
from app.domains.relationships.contracts.daily_review import manifest_digest
from app.domains.relationships.models.personalization import RelationshipReviewWork
from app.domains.relationships.policies.daily_review import partition_review_inputs


def review_children(db, work_id):
    return list(db.scalars(select(RelationshipReviewWork).where(
        RelationshipReviewWork.parent_id == work_id).order_by(RelationshipReviewWork.part_key)))

def new_work(db, *, world_id, actor_id, target_id, period_key, part_key, phase,
              manifest, view_version, parent_id=None):
    row = RelationshipReviewWork(id=uuid7_string(), world_id=world_id,
        actor_world_character_id=actor_id, target_world_character_id=target_id,
        period_key=period_key, part_key=part_key, phase=phase, manifest=manifest,
        manifest_digest=manifest_digest(manifest), expected_view_version=view_version,
        parent_id=parent_id, status="pending", attempts=0)
    db.add(row)
    db.flush()
    return row

def verified_result(work):
    result = {key: value for key, value in (work.result or {}).items() if key != "_execution"}
    expected = (work.result or {}).get("_execution", {}).get("result_digest")
    if expected != manifest_digest(result):
        raise ValueError("relationship_review_result_changed")
    return result

def build_payload(db, work):
    if manifest_digest(work.manifest) != work.manifest_digest:
        raise ValueError("relationship_review_manifest_changed")
    if work.phase == "direct":
        return {**work.manifest["base"], "memories": work.manifest["memories"]}
    if work.phase == "partial":
        return work.manifest["payload"]
    children = review_children(db, work.id)
    if not children or any(child.status != "ready" for child in children):
        return None
    base = work.manifest["base"]
    source_map = {memory["memory_id"]: memory["source_refs"] for memory in root_work(db, work).manifest["memories"]}
    entries = []
    for child in children:
        result = verified_result(child)
        entries.append({"part_id": child.id, **result, "source_refs": sorted({
            source for ref in result["memory_refs"] for source in source_map.get(ref, [])})})
    parts = partition_review_inputs(base, entries, key="partial_results")
    if len(parts) == 1:
        return parts[0]
    # Replace an oversized fan-in with bounded intermediate reductions. The
    # completed children keep their saved results and are never re-requested.
    if len(parts) >= len(children):
        raise ValueError("relationship_review_reduction_not_shrinking")
    for index, payload in enumerate(parts):
        group_ids = {entry["part_id"] for entry in payload["partial_results"]}
        reducer = new_work(db, world_id=work.world_id, actor_id=work.actor_world_character_id,
            target_id=work.target_world_character_id, period_key=work.period_key,
            part_key=f"reduce-{uuid7_string()}", phase="reduce", manifest={"base": base},
            view_version=work.expected_view_version, parent_id=work.id)
        for child in children:
            if child.id in group_ids:
                child.parent_id = reducer.id
    db.flush()
    return None

def root_work(db, work):
    seen = set()
    while work.parent_id is not None:
        if work.id in seen:
            raise ValueError("relationship_review_work_cycle")
        seen.add(work.id)
        work = db.get(RelationshipReviewWork, work.parent_id)
        if work is None:
            raise ValueError("relationship_review_parent_missing")
    return work
