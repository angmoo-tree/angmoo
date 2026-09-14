"""Private current-context receipts, separate from historical retrieval counts."""
import hashlib


def social_context_inspector(snapshot):
    if snapshot is None:
        return None
    return {
        "version": "evidence-inspector.v1",
        "items": [{
            "ref": "social-" + hashlib.sha256((snapshot.snapshot_id + item.relationship.relationship_state_id).encode()).hexdigest()[:32],
            "kind": "graph_relationship",
            "text": (f"답변 당시의 나 → {item.display_name}: 친숙도 {item.relationship.familiarity}, "
                     f"호감 {item.relationship.affinity}, 신뢰 {item.relationship.trust}, 긴장 {item.relationship.tension}. "
                     "선택된 현재 관계이며 전체 순위나 과거 사건의 근거가 아닙니다."),
            "occurred_at": snapshot.validated_at.isoformat(),
            "axes": [],
            "locator": {
                "kind": "graph_relationship", "source_type": None,
                "source_id": item.relationship.relationship_state_id,
                "source_revision": str(item.relationship.relationship_version),
                "actor_world_character_id": item.relationship.actor_world_character_id,
                "target_world_character_id": item.relationship.target_world_character_id,
            },
        } for item in snapshot.items],
    }
