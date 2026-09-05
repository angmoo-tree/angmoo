"""Routine context reads using exactly the caller's existing Session."""
from __future__ import annotations
from datetime import datetime
from typing import Any
from sqlalchemy import select
from app.domains.routines import models as routines_models
from app.domains.routines.contracts.lifecycle import EVENT_CONSUMPTION_NAMESPACE
from app.domains.worlds.models import World
from app.domains.world_characters.models import WorldActivityRepertoire, WorldCommunityProfile
from app.models.agent_settings import AgentActivitySetting
from app.runtime.routines.activity_references import SqlAlchemyActivityReferences
from app.compatibility.routine_posts.canonical_interactions import CanonicalRoutineInteractionSource
from app.domains.routine_posts.contracts.context import RoutineInteractionSource


class SqlAlchemyRoutineContextReferences(SqlAlchemyActivityReferences):
    def get_world(self, world_id: str) -> World | None:
        return self._db.get(World, world_id)

    def get_plan(self, plan_id: str) -> routines_models.DailyActivityPlan | None:
        return self._db.get(routines_models.DailyActivityPlan, plan_id)

    def get_repertoire(self, repertoire_id: str) -> WorldActivityRepertoire | None:
        return self._db.get(WorldActivityRepertoire, repertoire_id)

    def get_profile(self, profile_id: str) -> WorldCommunityProfile | None:
        return self._db.get(WorldCommunityProfile, profile_id)

    def get_beat(self, beat_id: str) -> routines_models.ActivityBeat | None:
        return self._db.get(routines_models.ActivityBeat, beat_id)

    def get_activity_setting(self, character_id: str) -> AgentActivitySetting | None:
        return self._db.get(AgentActivitySetting, character_id)

    def default_interaction_source(self) -> RoutineInteractionSource:
        return CanonicalRoutineInteractionSource()

    def current_item(self, *, world_character_id: str, current: datetime) -> routines_models.DailyActivityPlanItem | None:
        return self._db.scalar(
            select(routines_models.DailyActivityPlanItem).where(
                routines_models.DailyActivityPlanItem.world_character_id == world_character_id,
                routines_models.DailyActivityPlanItem.scheduled_start_at <= current,
                routines_models.DailyActivityPlanItem.scheduled_end_at > current,
                routines_models.DailyActivityPlanItem.status.in_({"planned", "active"}),
            )
        )

    def episode_for_item(self, plan_item_id: str) -> routines_models.ActivityEpisode | None:
        return self._db.scalar(
            select(routines_models.ActivityEpisode).where(
                routines_models.ActivityEpisode.plan_item_id == plan_item_id
            )
        )

    def latest_beat(self, episode_id: str) -> routines_models.ActivityBeat | None:
        return self._db.scalar(
            select(routines_models.ActivityBeat)
            .where(routines_models.ActivityBeat.episode_id == episode_id)
            .order_by(routines_models.ActivityBeat.scheduled_for.desc(), routines_models.ActivityBeat.id.desc())
            .limit(1)
        )

    def event_consumptions(self, *, world_character_id: str, event_ids: list[str]) -> Any:
        return self._db.scalars(
            select(routines_models.ActivityEventConsumption).where(
                routines_models.ActivityEventConsumption.consumer_world_character_id
                == world_character_id,
                routines_models.ActivityEventConsumption.source_social_event_id.in_(event_ids),
                routines_models.ActivityEventConsumption.namespace
                == EVENT_CONSUMPTION_NAMESPACE,
            )
        )
