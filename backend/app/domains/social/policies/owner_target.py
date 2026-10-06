"""One owner reply/reaction capability policy; no persistence or actor inference."""
def eligible_owner_target(*, target, membership, world_id: str, actor_id: str, blocked: bool) -> bool:
    return bool(target is not None and target.id != actor_id and target.world_id == world_id
        and target.status == "active" and target.control_mode == "autonomous"
        and target.activity_runtime_mode == "routine_resident_v1" and membership is not None
        and membership.world_id == world_id and membership.status == "active" and not blocked)
