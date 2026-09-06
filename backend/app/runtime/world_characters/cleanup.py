"""Cross-domain deletion composed in the caller-owned character transaction."""
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session
from app.domains.routines.models.plans import ActivityBeat as _model_ActivityBeat
from app.domains.routines.models.plans import ActivityEpisode as _model_ActivityEpisode
from app.domains.routines.models.plans import ActivityEventConsumption as _model_ActivityEventConsumption
from app.domains.routines.models.plans import ActivityPlanRevision as _model_ActivityPlanRevision
from app.domains.routines.models.resident import AgentPublicActionExecution as _model_AgentPublicActionExecution
from app.domains.routines.models.plans import DailyActivityPlan as _model_DailyActivityPlan
from app.domains.routines.models.plans import DailyActivityPlanItem as _model_DailyActivityPlanItem
from app.domains.routines.models.plans import JointActivity as _model_JointActivity
from app.domains.routines.models.plans import JointActivityParticipant as _model_JointActivityParticipant
from app.domains.routines.models.plans import JointActivityRepresentationClaim as _model_JointActivityRepresentationClaim
from app.domains.social.models.subjective_context import SocialActionSubjectiveContext as _model_SocialActionSubjectiveContext
from app.domains.world_characters.models import WorldActivityCandidate as _model_WorldActivityCandidate
from app.domains.world_characters.models import WorldActivityRepertoire as _model_WorldActivityRepertoire
from app.domains.world_characters.models import WorldCharacter as _model_WorldCharacter
from app.domains.social.models.feed import WorldCharacterBlock as _model_WorldCharacterBlock
from app.domains.social.models.feed import WorldCharacterFeedCursor as _model_WorldCharacterFeedCursor
from app.domains.social.models.feed import WorldCharacterFeedObservation as _model_WorldCharacterFeedObservation
from app.domains.world_characters.models import WorldCharacterSetupAttempt as _model_WorldCharacterSetupAttempt
from app.domains.world_characters.models import WorldCommunityProfile as _model_WorldCommunityProfile
from app.runtime.persistence.model_registration import register_models
register_models()


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
            select(_model_WorldCharacter.id).where(
                _model_WorldCharacter.character_id.in_(character_ids)
            )
        )
    )
    if not world_character_ids:
        return

    # Public-safe declarations remain private action state, not public posts.
    # Remove them before the legacy scrub path removes their executions.
    db.execute(
        delete(_model_SocialActionSubjectiveContext).where(
            _model_SocialActionSubjectiveContext.actor_world_character_id.in_(
                world_character_ids
            )
        )
    )

    # P5 feed cursors, claims, and blocks are private WorldCharacter runtime
    # state. Break the execution -> observation edge before deleting the
    # observation rows; account/Character deletion later removes the owned
    # executions through the existing scrub path.
    feed_observation_ids = list(
        db.scalars(
            select(_model_WorldCharacterFeedObservation.id).where(
                _model_WorldCharacterFeedObservation.observer_world_character_id.in_(
                    world_character_ids
                )
            )
        )
    )
    if feed_observation_ids:
        db.execute(
            update(_model_AgentPublicActionExecution)
            .where(
                _model_AgentPublicActionExecution.feed_observation_id.in_(
                    feed_observation_ids
                )
            )
            .values(feed_observation_id=None)
        )
        db.execute(
            delete(_model_WorldCharacterFeedObservation).where(
                _model_WorldCharacterFeedObservation.id.in_(feed_observation_ids)
            )
        )
    db.execute(
        delete(_model_WorldCharacterFeedCursor).where(
            _model_WorldCharacterFeedCursor.world_character_id.in_(
                world_character_ids
            )
        )
    )
    db.execute(
        delete(_model_WorldCharacterBlock).where(
            or_(
                _model_WorldCharacterBlock.blocker_world_character_id.in_(
                    world_character_ids
                ),
                _model_WorldCharacterBlock.blocked_world_character_id.in_(
                    world_character_ids
                ),
            )
        )
    )
    plan_ids = select(_model_DailyActivityPlan.id).where(
        _model_DailyActivityPlan.world_character_id.in_(world_character_ids)
    )
    item_ids = select(_model_DailyActivityPlanItem.id).where(
        _model_DailyActivityPlanItem.plan_id.in_(plan_ids)
    )
    episode_ids = select(_model_ActivityEpisode.id).where(
        _model_ActivityEpisode.plan_item_id.in_(item_ids)
    )
    beat_ids = select(_model_ActivityBeat.id).where(
        _model_ActivityBeat.episode_id.in_(episode_ids)
    )
    # Materialize this set before deleting participants.  A live subquery would
    # become empty after the participant delete and leave the shared activity
    # (and its links in another Character's plan) behind.
    joint_activity_ids = list(
        db.scalars(
            select(_model_JointActivityParticipant.joint_activity_id)
            .where(
                _model_JointActivityParticipant.world_character_id.in_(
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
        delete(_model_ActivityEventConsumption).where(
            _model_ActivityEventConsumption.consumer_world_character_id.in_(
                world_character_ids
            )
        )
    )
    db.execute(
        delete(_model_ActivityEventConsumption).where(
            _model_ActivityEventConsumption.target_activity_beat_id.in_(beat_ids)
        )
    )
    db.execute(
        delete(_model_ActivityBeat).where(_model_ActivityBeat.id.in_(beat_ids))
    )
    db.execute(
        delete(_model_JointActivityRepresentationClaim).where(
            _model_JointActivityRepresentationClaim.joint_activity_id.in_(
                joint_activity_ids
            )
        )
    )
    db.execute(
        delete(_model_ActivityPlanRevision).where(
            _model_ActivityPlanRevision.plan_id.in_(plan_ids)
        )
    )
    db.execute(
        delete(_model_ActivityPlanRevision).where(
            _model_ActivityPlanRevision.joint_activity_id.in_(joint_activity_ids)
        )
    )
    db.execute(
        delete(_model_JointActivityParticipant).where(
            _model_JointActivityParticipant.joint_activity_id.in_(joint_activity_ids)
        )
    )
    db.execute(
        update(_model_DailyActivityPlanItem)
        .where(_model_DailyActivityPlanItem.joint_activity_id.in_(joint_activity_ids))
        .values(joint_activity_id=None)
    )
    db.execute(
        delete(_model_ActivityEpisode).where(
            _model_ActivityEpisode.id.in_(episode_ids)
        )
    )
    db.execute(
        delete(_model_DailyActivityPlanItem).where(
            _model_DailyActivityPlanItem.id.in_(item_ids)
        )
    )
    db.execute(
        delete(_model_DailyActivityPlan).where(
            _model_DailyActivityPlan.id.in_(plan_ids)
        )
    )
    db.execute(
        delete(_model_JointActivity).where(
            _model_JointActivity.id.in_(joint_activity_ids)
        )
    )

    repertoire_ids = select(_model_WorldActivityRepertoire.id).where(
        _model_WorldActivityRepertoire.world_character_id.in_(world_character_ids)
    )
    db.execute(
        delete(_model_WorldActivityCandidate).where(
            _model_WorldActivityCandidate.repertoire_id.in_(repertoire_ids)
        )
    )
    db.execute(
        delete(_model_WorldActivityRepertoire).where(
            _model_WorldActivityRepertoire.world_character_id.in_(world_character_ids)
        )
    )
    db.execute(
        delete(_model_WorldCommunityProfile).where(
            _model_WorldCommunityProfile.world_character_id.in_(world_character_ids)
        )
    )
    db.execute(
        delete(_model_WorldCharacterSetupAttempt).where(
            _model_WorldCharacterSetupAttempt.world_character_id.in_(
                world_character_ids
            )
        )
    )


__all__ = ["delete_setup_data_for_characters"]
