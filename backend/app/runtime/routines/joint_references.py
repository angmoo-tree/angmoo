"""Foreign-row reads, Social owner writes and event composition on the caller's Session."""
from __future__ import annotations
from datetime import datetime
from hashlib import sha256
from typing import Any
from sqlalchemy import func, or_, select
from app.domains.social.models.posts import Post
from app.domains.social.models.feed import WorldCharacterBlock
from app.domains.worlds.models import WorldPlace
from app.domains.relationships.infrastructure.sqlalchemy_social_models import SocialEventEvidence
from app.domains.social.service import joint_posts, notifications
from app.runtime.relationships import sqlalchemy_social_event as social_event_runtime
from app.runtime.routines.activity_references import SqlAlchemyActivityReferences


class SqlAlchemyJointReferences(SqlAlchemyActivityReferences):
    def mutually_blocked(
        self, *, world_id: str, first_id: str, second_id: str
    ) -> bool:
        return (
            self._db.scalar(
                select(WorldCharacterBlock.id)
                .where(
                    WorldCharacterBlock.world_id == world_id,
                    or_(
                        (
                            WorldCharacterBlock.blocker_world_character_id
                            == first_id
                        )
                        & (
                            WorldCharacterBlock.blocked_world_character_id
                            == second_id
                        ),
                        (
                            WorldCharacterBlock.blocker_world_character_id
                            == second_id
                        )
                        & (
                            WorldCharacterBlock.blocked_world_character_id
                            == first_id
                        ),
                    ),
                )
                .limit(1)
            )
            is not None
        )
    def get_enabled_place(self, *, world_id: str, place_key: str) -> WorldPlace | None:
        return self._db.scalar(
            select(WorldPlace).where(
                WorldPlace.world_id == world_id,
                WorldPlace.place_key == place_key,
                WorldPlace.status == "enabled",
            )
        )

    def visible_joint_post_count(self, *, joint_activity_id: str) -> int:
        return int(
            self._db.scalar(
                select(func.count(Post.id)).where(
                    Post.joint_activity_id == joint_activity_id,
                    Post.deleted_at.is_(None),
                    Post.report_hidden_at.is_(None),
                )
            )
            or 0
        )

    def record_started_event(self, *, joint: Any, author_world_character_id: str, post: Any, post_event: Any, current: datetime) -> Any:
        return social_event_runtime.record_successful_social_event(
            self._db,
            world_id=joint.world_id,
            actor_world_character_id=author_world_character_id,
            target_world_character_id=None,
            event_type="joint_started",
            occurred_at=current,
            idempotency_key=sha256(f"joint-started|{joint.id}".encode("utf-8")).hexdigest(),
            evidence=social_event_runtime.EvidenceInput(
                evidence_kind="joint_activity",
                source_object_type="joint_activity",
                source_object_id=joint.id,
                root_post_id=post.id,
                source_post_id=post.id,
                agent_run_id=next(
                    (
                        evidence.agent_run_id
                        for evidence in self._db.scalars(
                            select(SocialEventEvidence).where(
                                SocialEventEvidence.social_event_id == post_event.id
                            )
                        )
                        if evidence.agent_run_id is not None
                    ),
                    None,
                ),
                source_visibility_at_event=post.visibility,
                source_author_id_at_event=author_world_character_id,
            ),
        ).event

    def record_completed_event(self, *, joint: Any, actor: Any, target: Any, current: datetime) -> None:
        social_event_runtime.record_successful_social_event(
            self._db,
            world_id=joint.world_id,
            actor_world_character_id=actor.world_character_id,
            target_world_character_id=target.world_character_id,
            event_type="joint_completed",
            occurred_at=current,
            idempotency_key=sha256(
                f"joint-completed|{joint.id}|{actor.world_character_id}".encode(
                    "utf-8"
                )
            ).hexdigest(),
            evidence=social_event_runtime.EvidenceInput(
                evidence_kind="joint_activity",
                source_object_type="joint_activity",
                source_object_id=joint.id,
                root_post_id=joint.opening_post_id,
                source_post_id=actor.last_joint_post_id or joint.opening_post_id,
                target_post_id=joint.opening_post_id,
                source_author_id_at_event=actor.world_character_id,
                source_visibility_at_event="public",
            ),
        )

    def set_joint_activity_id(self, post: Any, *, joint_activity_id: str) -> None:
        joint_posts.set_joint_activity_id(post, joint_activity_id=joint_activity_id)

    def set_opening_post_id(self, post: Any, *, opening_post_id: str) -> None:
        joint_posts.set_opening_post_id(post, opening_post_id=opening_post_id)

    def ensure_started_notification(self, *, joint_activity_id: str, world_id: str, recipient_world_character_id: str, actor_world_character_id: str, recipient_character_id: str, actor_character_id: str, source_social_event_id: str, post_id: str) -> None:
        notifications.ensure_joint_started_notification(
            self._db,
            joint_activity_id=joint_activity_id,
            world_id=world_id,
            recipient_world_character_id=recipient_world_character_id,
            actor_world_character_id=actor_world_character_id,
            recipient_character_id=recipient_character_id,
            actor_character_id=actor_character_id,
            source_social_event_id=source_social_event_id,
            post_id=post_id,
        )
