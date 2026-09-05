"""Character query and mutation entry points with caller-supplied runtime work.

Character ownership, list selection, profile/persona writes live here. Runtime
callbacks keep activity/credential/log/detail work in its existing transaction
order and receive exactly the same Session and attached Character.
"""
from sqlalchemy.orm import Session
from app.domains.characters import schemas
from app.domains.characters.contracts import CharacterOwner, CharacterManagementWorkflows
from app.domains.characters.service import access, mutations, profile


def _agent_list_sort_key(
    agent: schemas.AgentDetailRead,
) -> tuple[int, float, str, str]:
    is_running = agent.assigned_slot is not None and agent.assigned_slot.status == "running"
    recency_candidates = [
        value
        for value in (
            agent.assigned_slot.last_run_at if agent.assigned_slot else None,
            agent.activity_summary.last_activity_at,
        )
        if value is not None
    ]
    latest = max(recency_candidates) if recency_candidates else None
    latest_timestamp = latest.timestamp() if latest else 0.0
    return (
        0 if is_running else 1,
        -latest_timestamp,
        agent.character.name.casefold(),
        agent.character.id,
    )


def list_agents(
    db: Session,
    user: CharacterOwner,
    *,
    workflows: CharacterManagementWorkflows,
) -> list[schemas.AgentDetailRead]:
    agents = [
        workflows.build_detail(db, character)
        for character in profile.list_characters_for_user(db, user.id)
    ]
    return sorted(agents, key=_agent_list_sort_key)


def get_agent(
    db: Session,
    user: CharacterOwner,
    character_id: str,
    *,
    workflows: CharacterManagementWorkflows,
) -> schemas.AgentDetailRead:
    character = access._get_owned_character(db, user, character_id)
    return workflows.build_full_detail(db, character)


def create_agent(
    db: Session,
    user: CharacterOwner,
    data: schemas.AgentCreate,
    *,
    workflows: CharacterManagementWorkflows,
) -> schemas.AgentDetailRead:
    workflows.validate_initial_activity(data)
    character = mutations.create_owned_character(db, user, data)
    return workflows.after_create(db, user, character, data)


def update_profile(
    db: Session,
    user: CharacterOwner,
    character_id: str,
    data: schemas.AgentProfileUpdate,
    *,
    workflows: CharacterManagementWorkflows,
) -> schemas.AgentDetailRead:
    character, media_changed = mutations.update_owned_profile(db, user, character_id, data)
    return workflows.after_profile(db, user, character, media_changed)


def update_persona(
    db: Session,
    user: CharacterOwner,
    character_id: str,
    data: schemas.AgentPersonaUpdate,
    *,
    workflows: CharacterManagementWorkflows,
) -> schemas.AgentDetailRead:
    character = mutations.update_owned_persona(db, user, character_id, data)
    return workflows.after_persona(db, user, character)


def update_promotion_usage(
    db: Session,
    user: CharacterOwner,
    character_id: str,
    data: schemas.AgentPromotionUsageUpdate,
    *,
    workflows: CharacterManagementWorkflows,
) -> schemas.AgentDetailRead:
    character = mutations.update_owned_promotion(db, user, character_id, data)
    return workflows.build_detail(db, character)
