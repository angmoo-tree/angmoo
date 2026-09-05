from __future__ import annotations

from app.runtime.routines.joint_references import SqlAlchemyJointReferences

from datetime import date, datetime, timedelta
from functools import partial
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.runtime.relationships import (
    sqlalchemy_social_event as social_event_runtime,
)
from app.domains.routines.service import joint_activity as joint_activity_runtime
from app.services import (
    activity_proposal_runtime,
)
from routines.test_daily_activity_runtime import _engine, _prepare, _seed, _utc


def _joint_runtime_for_session(db: Session) -> SimpleNamespace:
    """Supply the transaction dependency before the unchanged behavioral assertion."""
    return SimpleNamespace(**{
        **vars(joint_activity_runtime),
        "apply_joint_post": partial(
            joint_activity_runtime.apply_joint_post,
            references=SqlAlchemyJointReferences(db),
        ),
    })


def _post(
    db: Session,
    *,
    post_id: str,
    fixture,
    body: str,
    created_at: datetime,
    reply_to_post_id: str | None = None,
) -> models.Post:
    row = models.Post(
        id=post_id,
        author_character_id=fixture.character.id,
        world_id=fixture.world_character.world_id,
        author_world_character_id=fixture.world_character.id,
        reply_to_post_id=reply_to_post_id,
        author_name=fixture.character.name,
        title="Joint academy activity",
        body=body,
        visibility="public",
        search_document=body,
        created_at=created_at,
    )
    db.add(row)
    db.flush()
    return row


def _record_post_event(
    db: Session,
    *,
    world_id: str,
    actor_world_character_id: str,
    target_world_character_id: str | None,
    event_type: str,
    source: models.Post,
    target_post_id: str | None,
    root_post_id: str,
    occurred_at: datetime,
    idempotency_key: str,
    interaction_intent: str | None = None,
    proposal_decision: str | None = None,
) -> models.SocialEvent:
    return social_event_runtime.record_successful_social_event(
        db,
        world_id=world_id,
        actor_world_character_id=actor_world_character_id,
        target_world_character_id=target_world_character_id,
        event_type=event_type,
        occurred_at=occurred_at,
        idempotency_key=idempotency_key,
        evidence=social_event_runtime.EvidenceInput(
            evidence_kind="post" if event_type == "post_published" else "reply_post",
            source_object_type="post",
            source_object_id=source.id,
            root_post_id=root_post_id,
            source_post_id=source.id,
            target_post_id=target_post_id,
            interaction_intent=interaction_intent,
            proposal_decision=proposal_decision,
            source_text=source.body,
            source_visibility_at_event="public",
            source_author_id_at_event=actor_world_character_id,
        ),
    ).event


def _published_proposal_fixture(
    db: Session,
    *,
    now: datetime,
    prefix: str,
) -> SimpleNamespace:
    world, proposer, acceptor = _seed(db, two_characters=True)
    assert acceptor is not None
    proposer_plan = _prepare(db, proposer, now=now, key=f"{prefix}-proposer-plan")
    acceptor_plan = _prepare(db, acceptor, now=now, key=f"{prefix}-acceptor-plan")
    root = _post(
        db,
        post_id=f"{prefix}-root",
        fixture=acceptor,
        body="I want to compare the observatory records.",
        created_at=now,
    )
    proposal_comment = _post(
        db,
        post_id=f"{prefix}-proposal-comment",
        fixture=proposer,
        body="Let's review the observatory records together this evening.",
        created_at=now + timedelta(minutes=1),
        reply_to_post_id=root.id,
    )
    proposal_event = _record_post_event(
        db,
        world_id=world.id,
        actor_world_character_id=proposer.world_character.id,
        target_world_character_id=acceptor.world_character.id,
        event_type="joint_proposed",
        source=proposal_comment,
        target_post_id=root.id,
        root_post_id=root.id,
        occurred_at=now + timedelta(minutes=1),
        idempotency_key=f"{prefix}-joint-proposed",
        interaction_intent="joint_activity_proposal",
    )
    preview = schemas.JointActivityProposalPreview(
        text=proposal_comment.body,
        source_post_id=root.id,
        activity_seed="Review the observatory records together.",
        target_world_character_id=acceptor.world_character.id,
        place_key=None,
        target_daypart="evening",
        date_policy="exact",
        target_date=date(2026, 8, 9),
    )
    proposal = activity_proposal_runtime.create_published_proposal(
        db,
        preview=preview,
        proposal_comment=proposal_comment,
        proposal_event=proposal_event,
        proposer_world_character_id=proposer.world_character.id,
        now=now + timedelta(minutes=1),
    )
    db.commit()
    return SimpleNamespace(
        world=world,
        proposer=proposer,
        acceptor=acceptor,
        proposer_plan=proposer_plan,
        acceptor_plan=acceptor_plan,
        root=root,
        proposal_comment=proposal_comment,
        proposal_event=proposal_event,
        proposal=proposal,
    )


def _ready_joint_fixture(
    db: Session,
    *,
    now: datetime,
    prefix: str,
) -> SimpleNamespace:
    fixture = _published_proposal_fixture(db, now=now, prefix=prefix)
    schedule = activity_proposal_runtime.resolve_acceptance_schedule(
        db,
        proposal_id=fixture.proposal.id,
        now=now + timedelta(minutes=2),
    )
    acceptance_comment = _post(
        db,
        post_id=f"{prefix}-acceptance-comment",
        fixture=fixture.acceptor,
        body="Yes, let's meet this evening and compare them.",
        created_at=now + timedelta(minutes=3),
        reply_to_post_id=fixture.proposal_comment.id,
    )
    acceptance_event = _record_post_event(
        db,
        world_id=fixture.world.id,
        actor_world_character_id=fixture.acceptor.world_character.id,
        target_world_character_id=fixture.proposer.world_character.id,
        event_type="joint_accepted",
        source=acceptance_comment,
        target_post_id=fixture.proposal_comment.id,
        root_post_id=fixture.root.id,
        occurred_at=now + timedelta(minutes=3),
        idempotency_key=f"{prefix}-joint-accepted",
        proposal_decision="accept",
    )
    accepted = activity_proposal_runtime.apply_response(
        db,
        proposal_id=fixture.proposal.id,
        response_event=acceptance_event,
        decision="accept",
        resolved_schedule=schedule,
        now=now + timedelta(minutes=3),
    )
    db.commit()
    assert accepted.joint_activity is not None
    fixture.schedule = schedule
    fixture.acceptance_comment = acceptance_comment
    fixture.acceptance_event = acceptance_event
    fixture.joint = accepted.joint_activity
    return fixture


def test_proposal_acceptance_enters_both_plans_and_both_characters_continue_joint_episode() -> None:
    engine = _engine()
    now = _utc(datetime(2026, 8, 9, 0, 30))
    with Session(engine, expire_on_commit=False) as db:
        joint_activity_runtime = _joint_runtime_for_session(db)
        world, proposer, acceptor = _seed(db, two_characters=True)
        assert acceptor is not None
        proposer_plan = _prepare(db, proposer, now=now, key="p6-plan-proposer")
        acceptor_plan = _prepare(db, acceptor, now=now, key="p6-plan-acceptor")
        root = _post(
            db,
            post_id="p6-proposal-root",
            fixture=acceptor,
            body="I want to compare the observatory records.",
            created_at=now,
        )
        proposal_comment = _post(
            db,
            post_id="p6-proposal-comment",
            fixture=proposer,
            body="Let's review the observatory records together this evening.",
            created_at=now + timedelta(minutes=1),
            reply_to_post_id=root.id,
        )
        proposal_event = _record_post_event(
            db,
            world_id=world.id,
            actor_world_character_id=proposer.world_character.id,
            target_world_character_id=acceptor.world_character.id,
            event_type="joint_proposed",
            source=proposal_comment,
            target_post_id=root.id,
            root_post_id=root.id,
            occurred_at=now + timedelta(minutes=1),
            idempotency_key="p6-joint-proposed",
            interaction_intent="joint_activity_proposal",
        )
        preview = schemas.JointActivityProposalPreview(
            text=proposal_comment.body,
            source_post_id=root.id,
            activity_seed="Review the observatory records together.",
            target_world_character_id=acceptor.world_character.id,
            place_key=None,
            target_daypart="evening",
            date_policy="exact",
            target_date=date(2026, 8, 9),
        )
        proposal = activity_proposal_runtime.create_published_proposal(
            db,
            preview=preview,
            proposal_comment=proposal_comment,
            proposal_event=proposal_event,
            proposer_world_character_id=proposer.world_character.id,
            now=now + timedelta(minutes=1),
        )
        db.commit()

        schedule = activity_proposal_runtime.resolve_acceptance_schedule(
            db,
            proposal_id=proposal.id,
            now=now + timedelta(minutes=2),
        )
        acceptance_comment = _post(
            db,
            post_id="p6-acceptance-comment",
            fixture=acceptor,
            body="Yes, let's meet this evening and compare them.",
            created_at=now + timedelta(minutes=3),
            reply_to_post_id=proposal_comment.id,
        )
        acceptance_event = _record_post_event(
            db,
            world_id=world.id,
            actor_world_character_id=acceptor.world_character.id,
            target_world_character_id=proposer.world_character.id,
            event_type="joint_accepted",
            source=acceptance_comment,
            target_post_id=proposal_comment.id,
            root_post_id=root.id,
            occurred_at=now + timedelta(minutes=3),
            idempotency_key="p6-joint-accepted",
            proposal_decision="accept",
        )
        accepted = activity_proposal_runtime.apply_response(
            db,
            proposal_id=proposal.id,
            response_event=acceptance_event,
            decision="accept",
            resolved_schedule=schedule,
            now=now + timedelta(minutes=3),
        )
        db.commit()

        joint = accepted.joint_activity
        assert joint is not None
        assert proposal.status == "accepted"
        assert joint.status == "ready"
        assert joint.scheduled_local_date == date(2026, 8, 9)
        assert joint.target_daypart == "evening"
        participants = list(
            db.scalars(
                select(models.JointActivityParticipant)
                .where(models.JointActivityParticipant.joint_activity_id == joint.id)
                .order_by(models.JointActivityParticipant.role)
            )
        )
        assert len(participants) == 2
        assert all(row.linked_daily_activity_plan_item_id for row in participants)
        assert all(row.linked_activity_episode_id for row in participants)
        assert db.scalar(
            select(func.count(models.DailyActivityPlanItem.id)).where(
                models.DailyActivityPlanItem.joint_activity_id == joint.id,
                models.DailyActivityPlanItem.origin_type == "joint_activity",
            )
        ) == 2
        assert db.scalar(
            select(func.count(models.DailyActivityPlanItem.id)).where(
                models.DailyActivityPlanItem.plan_id.in_(
                    (proposer_plan.id, acceptor_plan.id)
                ),
                models.DailyActivityPlanItem.daypart == "evening",
                models.DailyActivityPlanItem.status == "superseded",
            )
        ) == 2
        assert db.scalar(select(func.count(models.ActivityPlanRevision.id))) == 2

        opening_time = schedule.scheduled_start_at + timedelta(minutes=5)
        opening_claim = joint_activity_runtime.claim_opening(
            db, references=SqlAlchemyJointReferences(db),
            joint_activity_id=joint.id,
            claimant_world_character_id=proposer.world_character.id,
            now=opening_time,
        )
        opening_post = _post(
            db,
            post_id="p6-joint-opening",
            fixture=proposer,
            body="We started comparing the first observatory record.",
            created_at=opening_time,
        )
        opening_post_event = _record_post_event(
            db,
            world_id=world.id,
            actor_world_character_id=proposer.world_character.id,
            target_world_character_id=None,
            event_type="post_published",
            source=opening_post,
            target_post_id=None,
            root_post_id=opening_post.id,
            occurred_at=opening_time,
            idempotency_key="p6-joint-opening-post",
        )
        started_event = joint_activity_runtime.apply_joint_post(
            db, references=SqlAlchemyJointReferences(db),
            joint_activity_id=joint.id,
            author_world_character_id=proposer.world_character.id,
            post=opening_post,
            post_event=opening_post_event,
            opening_claim=opening_claim,
            now=opening_time,
        )
        db.commit()

        assert started_event is not None
        assert started_event.event_type == "joint_started"
        assert joint.status == "active"
        assert joint.opening_post_id == opening_post.id
        assert all(
            db.get(
                models.DailyActivityPlanItem,
                participant.linked_daily_activity_plan_item_id,
            ).status
            == "active"
            for participant in participants
        )

        followup_time = opening_time + timedelta(hours=1)
        followup_post = _post(
            db,
            post_id="p6-joint-followup",
            fixture=acceptor,
            body="From my side, the second record confirms the same pattern.",
            created_at=followup_time,
        )
        followup_event = _record_post_event(
            db,
            world_id=world.id,
            actor_world_character_id=acceptor.world_character.id,
            target_world_character_id=None,
            event_type="post_published",
            source=followup_post,
            target_post_id=None,
            root_post_id=followup_post.id,
            occurred_at=followup_time,
            idempotency_key="p6-joint-followup-post",
        )
        assert (
            joint_activity_runtime.apply_joint_post(
                db,
                joint_activity_id=joint.id,
                author_world_character_id=acceptor.world_character.id,
                post=followup_post,
                post_event=followup_event,
                opening_claim=None,
                now=followup_time,
            )
            is None
        )
        db.commit()

        assert followup_post.opening_post_id == opening_post.id
        assert opening_post.id != followup_post.id
        completed, expired = joint_activity_runtime.complete_due_joint_activities(
            db, references=SqlAlchemyJointReferences(db),
            world_id=world.id,
            now=schedule.scheduled_end_at + timedelta(minutes=1),
        )
        assert (completed, expired) == (1, 0)
        assert joint.status == "completed"
        assert db.scalar(
            select(func.count(models.SocialEvent.id)).where(
                models.SocialEvent.event_type == "joint_completed"
            )
        ) == 2
        assert db.scalar(
            select(func.count(models.SocialEvent.id)).where(
                models.SocialEvent.event_type == "joint_started"
            )
        ) == 1
        assert db.scalar(
            select(func.count(models.Notification.id)).where(
                models.Notification.notification_type == "joint_activity_started",
                models.Notification.recipient_world_character_id
                == acceptor.world_character.id,
            )
        ) == 1
        proposer_to_acceptor = db.scalar(
            select(models.RelationshipState).where(
                models.RelationshipState.actor_world_character_id
                == proposer.world_character.id,
                models.RelationshipState.target_world_character_id
                == acceptor.world_character.id,
            )
        )
        acceptor_to_proposer = db.scalar(
            select(models.RelationshipState).where(
                models.RelationshipState.actor_world_character_id
                == acceptor.world_character.id,
                models.RelationshipState.target_world_character_id
                == proposer.world_character.id,
            )
        )
        assert proposer_to_acceptor is not None
        assert acceptor_to_proposer is not None
        assert (
            proposer_to_acceptor.familiarity,
            proposer_to_acceptor.affinity,
            proposer_to_acceptor.trust,
        ) == (4, 2, 3)
        assert (
            acceptor_to_proposer.familiarity,
            acceptor_to_proposer.affinity,
            acceptor_to_proposer.trust,
        ) == (6, 2, 4)
        assert db.scalar(
            select(func.count(models.DailyActivityPlanItem.id)).where(
                models.DailyActivityPlanItem.joint_activity_id == joint.id,
                models.DailyActivityPlanItem.status == "completed",
            )
        ) == 2


def test_failed_proposal_publish_rolls_back_proposal_event_and_relationship() -> None:
    engine = _engine()
    now = _utc(datetime(2026, 8, 9, 0, 30))
    with Session(engine, expire_on_commit=False) as db:
        world, proposer, acceptor = _seed(db, two_characters=True)
        assert acceptor is not None
        root = _post(
            db,
            post_id="p6-publish-failure-root",
            fixture=acceptor,
            body="I want to compare the observatory records.",
            created_at=now,
        )
        db.commit()

        proposal_comment = _post(
            db,
            post_id="p6-publish-failure-comment",
            fixture=proposer,
            body="Let's review the observatory records together this evening.",
            created_at=now + timedelta(minutes=1),
            reply_to_post_id=root.id,
        )
        proposal_event = _record_post_event(
            db,
            world_id=world.id,
            actor_world_character_id=proposer.world_character.id,
            target_world_character_id=acceptor.world_character.id,
            event_type="joint_proposed",
            source=proposal_comment,
            target_post_id=root.id,
            root_post_id=root.id,
            occurred_at=now + timedelta(minutes=1),
            idempotency_key="rollback",
            interaction_intent="joint_activity_proposal",
        )
        proposal = activity_proposal_runtime.create_published_proposal(
            db,
            preview=schemas.JointActivityProposalPreview(
                text=proposal_comment.body,
                source_post_id=root.id,
                activity_seed="Review the observatory records together.",
                target_world_character_id=acceptor.world_character.id,
                place_key=None,
                target_daypart="evening",
                date_policy="exact",
                target_date=date(2026, 8, 9),
            ),
            proposal_comment=proposal_comment,
            proposal_event=proposal_event,
            proposer_world_character_id=proposer.world_character.id,
            now=now + timedelta(minutes=1),
        )
        proposal_id = proposal.id
        proposal_event_id = proposal_event.id
        db.rollback()

        assert db.get(models.Post, root.id) is not None
        assert db.get(models.Post, "p6-publish-failure-comment") is None
        assert db.get(models.SocialEvent, proposal_event_id) is None
        assert db.get(models.ActivityProposal, proposal_id) is None
        assert db.scalar(select(func.count(models.RelationshipState.id))) == 0
        assert db.scalar(select(func.count(models.RelationshipStateChange.id))) == 0
        assert db.scalar(select(func.count(models.GraphProjectionOutbox.id))) == 0
        assert db.scalar(select(func.count(models.JointActivity.id))) == 0
        assert db.scalar(select(func.count(models.ActivityPlanRevision.id))) == 0


def test_exact_schedule_failure_rolls_back_acceptance_and_plan_revision() -> None:
    engine = _engine()
    now = _utc(datetime(2026, 8, 9, 0, 30))
    with Session(engine, expire_on_commit=False) as db:
        fixture = _published_proposal_fixture(
            db,
            now=now,
            prefix="p6-exact-schedule-failure",
        )
        before_relationship_changes = int(
            db.scalar(select(func.count(models.RelationshipStateChange.id))) or 0
        )
        failed_at = _utc(datetime(2026, 8, 9, 19, 0))
        acceptance_comment = _post(
            db,
            post_id="p6-exact-schedule-failure-acceptance",
            fixture=fixture.acceptor,
            body="Yes, let's meet this evening and compare them.",
            created_at=failed_at,
            reply_to_post_id=fixture.proposal_comment.id,
        )
        acceptance_event = _record_post_event(
            db,
            world_id=fixture.world.id,
            actor_world_character_id=fixture.acceptor.world_character.id,
            target_world_character_id=fixture.proposer.world_character.id,
            event_type="joint_accepted",
            source=acceptance_comment,
            target_post_id=fixture.proposal_comment.id,
            root_post_id=fixture.root.id,
            occurred_at=failed_at,
            idempotency_key="p6-exact-schedule-failure-accepted",
            proposal_decision="accept",
        )
        acceptance_event_id = acceptance_event.id

        with pytest.raises(
            activity_proposal_runtime.ActivityProposalRuntimeError,
            match="joint_activity_no_shared_schedule",
        ):
            activity_proposal_runtime.apply_response(
                db,
                proposal_id=fixture.proposal.id,
                response_event=acceptance_event,
                decision="accept",
                now=failed_at,
            )
        db.rollback()

        proposal = db.get(models.ActivityProposal, fixture.proposal.id)
        assert proposal is not None
        assert proposal.status == "proposed"
        assert proposal.source_response_event_id is None
        assert db.get(models.Post, acceptance_comment.id) is None
        assert db.get(models.SocialEvent, acceptance_event_id) is None
        assert db.scalar(select(func.count(models.JointActivity.id))) == 0
        assert db.scalar(select(func.count(models.JointActivityParticipant.joint_activity_id))) == 0
        assert db.scalar(select(func.count(models.ActivityPlanRevision.id))) == 0
        assert (
            int(db.scalar(select(func.count(models.RelationshipStateChange.id))) or 0)
            == before_relationship_changes
        )


def test_zero_joint_posts_expire_without_completion_event_or_relationship_delta() -> None:
    engine = _engine()
    now = _utc(datetime(2026, 8, 9, 0, 30))
    with Session(engine, expire_on_commit=False) as db:
        fixture = _ready_joint_fixture(
            db,
            now=now,
            prefix="p6-zero-joint-posts",
        )
        relationship_before = {
            row.id: (
                row.familiarity,
                row.affinity,
                row.trust,
                row.tension,
                row.interaction_count,
                row.version,
            )
            for row in db.scalars(select(models.RelationshipState))
        }
        changes_before = int(
            db.scalar(select(func.count(models.RelationshipStateChange.id))) or 0
        )
        assert (
            db.scalar(
                select(func.count(models.Post.id)).where(
                    models.Post.joint_activity_id == fixture.joint.id
                )
            )
            == 0
        )

        completed, expired = joint_activity_runtime.complete_due_joint_activities(
            db, references=SqlAlchemyJointReferences(db),
            world_id=fixture.world.id,
            now=fixture.schedule.scheduled_end_at + timedelta(minutes=1),
        )
        db.expire_all()

        joint = db.get(models.JointActivity, fixture.joint.id)
        participants = list(
            db.scalars(
                select(models.JointActivityParticipant).where(
                    models.JointActivityParticipant.joint_activity_id
                    == fixture.joint.id
                )
            )
        )
        assert (completed, expired) == (0, 1)
        assert joint is not None and joint.status == "expired_unrepresented"
        assert all(row.participation_status == "interrupted" for row in participants)
        assert all(
            db.get(
                models.DailyActivityPlanItem,
                row.linked_daily_activity_plan_item_id,
            ).status
            == "skipped"
            for row in participants
        )
        assert all(
            db.get(
                models.DailyActivityPlanItem,
                row.linked_daily_activity_plan_item_id,
            ).terminal_reason_code
            == "joint_unrepresented"
            for row in participants
        )
        assert all(
            db.get(models.ActivityEpisode, row.linked_activity_episode_id).status
            == "interrupted"
            for row in participants
        )
        assert all(
            db.get(
                models.ActivityEpisode,
                row.linked_activity_episode_id,
            ).terminal_reason_code
            == "joint_unrepresented"
            for row in participants
        )
        assert (
            db.scalar(
                select(func.count(models.SocialEvent.id)).where(
                    models.SocialEvent.event_type == "joint_completed"
                )
            )
            == 0
        )
        assert {
            row.id: (
                row.familiarity,
                row.affinity,
                row.trust,
                row.tension,
                row.interaction_count,
                row.version,
            )
            for row in db.scalars(select(models.RelationshipState))
        } == relationship_before
        assert (
            int(db.scalar(select(func.count(models.RelationshipStateChange.id))) or 0)
            == changes_before
        )


def test_opening_and_followup_failures_preserve_joint_and_both_participant_plans() -> None:
    engine = _engine()
    now = _utc(datetime(2026, 8, 9, 0, 30))
    with Session(engine, expire_on_commit=False) as db:
        fixture = _ready_joint_fixture(
            db,
            now=now,
            prefix="p6-joint-write-failures",
        )
        first_attempt_at = fixture.schedule.scheduled_start_at + timedelta(minutes=5)
        failed_claim = joint_activity_runtime.claim_opening(
            db, references=SqlAlchemyJointReferences(db),
            joint_activity_id=fixture.joint.id,
            claimant_world_character_id=fixture.proposer.world_character.id,
            now=first_attempt_at,
        )
        joint_activity_runtime.release_opening(db, claim=failed_claim)
        db.expire_all()

        joint = db.get(models.JointActivity, fixture.joint.id)
        claim = db.get(
            models.JointActivityRepresentationClaim,
            fixture.joint.id,
        )
        participants = list(
            db.scalars(
                select(models.JointActivityParticipant).where(
                    models.JointActivityParticipant.joint_activity_id
                    == fixture.joint.id
                )
            )
        )
        assert joint is not None and joint.status == "ready"
        assert joint.opening_post_id is None
        assert claim is not None and claim.representation_status == "pending"
        assert claim.claimed_by_world_character_id is None
        assert (
            db.scalar(
                select(func.count(models.Post.id)).where(
                    models.Post.joint_activity_id == fixture.joint.id
                )
            )
            == 0
        )
        assert (
            db.scalar(
                select(func.count(models.SocialEvent.id)).where(
                    models.SocialEvent.event_type == "joint_started"
                )
            )
            == 0
        )
        assert all(
            db.get(
                models.DailyActivityPlanItem,
                row.linked_daily_activity_plan_item_id,
            ).status
            == "planned"
            for row in participants
        )
        assert all(
            db.get(models.ActivityEpisode, row.linked_activity_episode_id).status
            == "planned"
            for row in participants
        )

        opening_at = first_attempt_at + timedelta(minutes=5)
        opening_claim = joint_activity_runtime.claim_opening(
            db, references=SqlAlchemyJointReferences(db),
            joint_activity_id=fixture.joint.id,
            claimant_world_character_id=fixture.proposer.world_character.id,
            now=opening_at,
        )
        opening_post = _post(
            db,
            post_id="p6-joint-write-failures-opening",
            fixture=fixture.proposer,
            body="We started comparing the first observatory record.",
            created_at=opening_at,
        )
        opening_event = _record_post_event(
            db,
            world_id=fixture.world.id,
            actor_world_character_id=fixture.proposer.world_character.id,
            target_world_character_id=None,
            event_type="post_published",
            source=opening_post,
            target_post_id=None,
            root_post_id=opening_post.id,
            occurred_at=opening_at,
            idempotency_key="p6-joint-write-failures-opening-post",
        )
        joint_activity_runtime.apply_joint_post(
            db, references=SqlAlchemyJointReferences(db),
            joint_activity_id=fixture.joint.id,
            author_world_character_id=fixture.proposer.world_character.id,
            post=opening_post,
            post_event=opening_event,
            opening_claim=opening_claim,
            now=opening_at,
        )
        db.commit()

        followup_at = opening_at + timedelta(hours=1)
        followup_post = _post(
            db,
            post_id="p6-joint-write-failures-followup",
            fixture=fixture.acceptor,
            body="The second record confirms the same pattern.",
            created_at=followup_at,
        )
        followup_event = _record_post_event(
            db,
            world_id=fixture.world.id,
            actor_world_character_id=fixture.acceptor.world_character.id,
            target_world_character_id=None,
            event_type="post_published",
            source=followup_post,
            target_post_id=None,
            root_post_id=followup_post.id,
            occurred_at=followup_at,
            idempotency_key="p6-joint-write-failures-followup-post",
        )
        followup_event_id = followup_event.id
        joint_activity_runtime.apply_joint_post(
            db, references=SqlAlchemyJointReferences(db),
            joint_activity_id=fixture.joint.id,
            author_world_character_id=fixture.acceptor.world_character.id,
            post=followup_post,
            post_event=followup_event,
            opening_claim=None,
            now=followup_at,
        )
        db.rollback()
        db.expire_all()

        joint = db.get(models.JointActivity, fixture.joint.id)
        participants = list(
            db.scalars(
                select(models.JointActivityParticipant).where(
                    models.JointActivityParticipant.joint_activity_id
                    == fixture.joint.id
                )
            )
        )
        assert db.get(models.Post, "p6-joint-write-failures-followup") is None
        assert db.get(models.SocialEvent, followup_event_id) is None
        assert joint is not None and joint.status == "active"
        assert joint.opening_post_id == opening_post.id
        assert all(row.participation_status == "active" for row in participants)
        assert all(
            db.get(
                models.DailyActivityPlanItem,
                row.linked_daily_activity_plan_item_id,
            ).status
            == "active"
            for row in participants
        )
        assert all(
            db.get(models.ActivityEpisode, row.linked_activity_episode_id).status
            == "active"
            for row in participants
        )
        assert (
            db.scalar(
                select(func.count(models.DailyActivityPlanItem.id)).where(
                    models.DailyActivityPlanItem.joint_activity_id == fixture.joint.id,
                    models.DailyActivityPlanItem.status == "completed",
                )
            )
            == 0
        )
