"""Compatibility facade for the canonical WorldCharacter setup domain."""

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app import models
from app.domains.world_characters.public import (
    OWNER_REGENERATION_LIMIT_24H,
    PROFILE_REGENERATION_LIMIT_24H,
    WorldCharacterSetupConflictError,
    WorldCharacterSetupError,
    WorldCharacterSetupForbiddenError,
    WorldCharacterSetupNotFoundError,
    WorldCharacterSetupValidationError,
    approve_setup,
    enter_world,
    generate_setup,
    get_setup,
    get_world_entry,
    preflight_setup,
    reject_setup,
    retry_setup,
)
def delete_setup_data_for_characters(
    db: Session,
    *,
    character_ids: list[str],
) -> None:
    """Delete private P2/P3 outputs before a Character is scrubbed."""
    if not character_ids:
        return
    world_character_ids = list(
        db.scalars(
            select(models.WorldCharacter.id).where(
                models.WorldCharacter.character_id.in_(character_ids)
            )
        )
    )
    if not world_character_ids:
        return

    # P5 feed cursors, claims, and blocks are private WorldCharacter runtime
    # state. Break the execution -> observation edge before deleting the
    # observation rows; account/Character deletion later removes the owned
    # executions through the existing scrub path.
    feed_observation_ids = list(
        db.scalars(
            select(models.WorldCharacterFeedObservation.id).where(
                models.WorldCharacterFeedObservation.observer_world_character_id.in_(
                    world_character_ids
                )
            )
        )
    )
    if feed_observation_ids:
        db.execute(
            update(models.AgentPublicActionExecution)
            .where(
                models.AgentPublicActionExecution.feed_observation_id.in_(
                    feed_observation_ids
                )
            )
            .values(feed_observation_id=None)
        )
        db.execute(
            delete(models.WorldCharacterFeedObservation).where(
                models.WorldCharacterFeedObservation.id.in_(feed_observation_ids)
            )
        )
    db.execute(
        delete(models.WorldCharacterFeedCursor).where(
            models.WorldCharacterFeedCursor.world_character_id.in_(
                world_character_ids
            )
        )
    )
    db.execute(
        delete(models.WorldCharacterBlock).where(
            or_(
                models.WorldCharacterBlock.blocker_world_character_id.in_(
                    world_character_ids
                ),
                models.WorldCharacterBlock.blocked_world_character_id.in_(
                    world_character_ids
                ),
            )
        )
    )
    plan_ids = select(models.DailyActivityPlan.id).where(
        models.DailyActivityPlan.world_character_id.in_(world_character_ids)
    )
    item_ids = select(models.DailyActivityPlanItem.id).where(
        models.DailyActivityPlanItem.plan_id.in_(plan_ids)
    )
    episode_ids = select(models.ActivityEpisode.id).where(
        models.ActivityEpisode.plan_item_id.in_(item_ids)
    )
    beat_ids = select(models.ActivityBeat.id).where(
        models.ActivityBeat.episode_id.in_(episode_ids)
    )
    # Materialize this set before deleting participants.  A live subquery would
    # become empty after the participant delete and leave the shared activity
    # (and its links in another Character's plan) behind.
    joint_activity_ids = list(
        db.scalars(
            select(models.JointActivityParticipant.joint_activity_id)
            .where(
                models.JointActivityParticipant.world_character_id.in_(
                    world_character_ids
                )
            )
            .distinct()
        )
    )

    # P3 runtime rows are private execution state.  Remove claims and ledgers
    # before their scoped plan rows, and detach a shared participant's item
    # before deleting a joint activity involving the scrubbed Character.
    db.execute(
        delete(models.ActivityEventConsumption).where(
            models.ActivityEventConsumption.consumer_world_character_id.in_(
                world_character_ids
            )
        )
    )
    db.execute(
        delete(models.ActivityEventConsumption).where(
            models.ActivityEventConsumption.target_activity_beat_id.in_(beat_ids)
        )
    )
    db.execute(
        delete(models.ActivityBeat).where(models.ActivityBeat.id.in_(beat_ids))
    )
    db.execute(
        delete(models.JointActivityRepresentationClaim).where(
            models.JointActivityRepresentationClaim.joint_activity_id.in_(
                joint_activity_ids
            )
        )
    )
    db.execute(
        delete(models.ActivityPlanRevision).where(
            models.ActivityPlanRevision.plan_id.in_(plan_ids)
        )
    )
    db.execute(
        delete(models.ActivityPlanRevision).where(
            models.ActivityPlanRevision.joint_activity_id.in_(joint_activity_ids)
        )
    )
    db.execute(
        delete(models.JointActivityParticipant).where(
            models.JointActivityParticipant.joint_activity_id.in_(joint_activity_ids)
        )
    )
    db.execute(
        update(models.DailyActivityPlanItem)
        .where(models.DailyActivityPlanItem.joint_activity_id.in_(joint_activity_ids))
        .values(joint_activity_id=None)
    )
    db.execute(
        delete(models.ActivityEpisode).where(
            models.ActivityEpisode.id.in_(episode_ids)
        )
    )
    db.execute(
        delete(models.DailyActivityPlanItem).where(
            models.DailyActivityPlanItem.id.in_(item_ids)
        )
    )
    db.execute(
        delete(models.DailyActivityPlan).where(
            models.DailyActivityPlan.id.in_(plan_ids)
        )
    )
    db.execute(
        delete(models.JointActivity).where(
            models.JointActivity.id.in_(joint_activity_ids)
        )
    )

    repertoire_ids = select(models.WorldActivityRepertoire.id).where(
        models.WorldActivityRepertoire.world_character_id.in_(world_character_ids)
    )
    db.execute(
        delete(models.WorldActivityCandidate).where(
            models.WorldActivityCandidate.repertoire_id.in_(repertoire_ids)
        )
    )
    db.execute(
        delete(models.WorldActivityRepertoire).where(
            models.WorldActivityRepertoire.world_character_id.in_(world_character_ids)
        )
    )
    db.execute(
        delete(models.WorldCommunityProfile).where(
            models.WorldCommunityProfile.world_character_id.in_(world_character_ids)
        )
    )
    db.execute(
        delete(models.WorldCharacterSetupAttempt).where(
            models.WorldCharacterSetupAttempt.world_character_id.in_(
                world_character_ids
            )
        )
    )


__all__ = [
    "OWNER_REGENERATION_LIMIT_24H",
    "PROFILE_REGENERATION_LIMIT_24H",
    "WorldCharacterSetupConflictError",
    "WorldCharacterSetupError",
    "WorldCharacterSetupForbiddenError",
    "WorldCharacterSetupNotFoundError",
    "WorldCharacterSetupValidationError",
    "approve_setup",
    "delete_setup_data_for_characters",
    "enter_world",
    "generate_setup",
    "get_setup",
    "get_world_entry",
    "preflight_setup",
    "reject_setup",
    "retry_setup",
]
