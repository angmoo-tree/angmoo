"""One saved-facts decision for inspection, dashboard and explicit ON admission."""


def activation_reason(*, world, actor, character, policy_valid, credential_valid, readiness, maintenance):
    if world.status != "published":
        return "world_not_published"
    if actor is None or actor.status != "active" or actor.control_mode != "autonomous":
        return "world_character_not_ready"
    if character.execution_mode != "llm":
        return "world_activity_not_ready"
    if not policy_valid:
        return "world_activity_policy_invalid"
    if not credential_valid:
        return "credential_required"
    if not readiness.ready:
        return readiness.reason_code or "world_activity_not_ready"
    if maintenance:
        return "activity_maintenance"
    return None
