"""Bound public context and validate generation against server-owned evidence."""
from __future__ import annotations
from copy import deepcopy
from typing import Any
from app.domains.routine_posts import schemas
from app.domains.routine_posts.constants import ROUTINE_CONTRACT_VERSION
from app.domains.routine_posts.contracts.context import RoutinePostContext
from app.domains.routine_posts.contracts.generation import RoutineGeneration
from app.domains.routine_posts.utils.text import _clip
from app.domains.routines import service as activity_state_contracts
from app.providers.gemini import build_gemini_developer_response_schema


GEMINI_ROUTINE_BEAT_PLAN_RESPONSE_SCHEMA = (
    build_gemini_developer_response_schema(schemas.RoutineBeatPlan)
)


GEMINI_ROUTINE_POST_DRAFT_RESPONSE_SCHEMA = (
    build_gemini_developer_response_schema(schemas.RoutinePostDraft)
)


def _common_context(context: RoutinePostContext) -> dict[str, object]:
    return {
        "contract_version": ROUTINE_CONTRACT_VERSION,
        "world": {
            "id": context.world.id,
            "name": _clip(context.world.name, 120),
            "tagline": _clip(context.world.tagline, 160),
            "setting_description": _clip(context.world.setting_description, 1_500),
            "daily_life_description": _clip(
                context.world.daily_life_description, 1_500
            ),
            "tone_tags": list(context.world.tone_tags)[:12],
            "timezone": context.world.timezone,
        },
        "character": {
            "id": context.character.id,
            "name": _clip(context.character.name, 80),
            "persona_summary": _clip(context.character.persona_summary, 1_500),
            "speech_style": _clip(context.character.speech_style, 800),
            "world_local_profile": context.world_character.local_profile or {},
            "community_profile": {
                "visible_summary": _clip(context.profile.visible_summary, 280),
                "core_interests": list(context.profile.core_interests)[:8],
                "action_profile": context.profile.action_profile,
            },
        },
        "activity": {
            "daypart": context.item.daypart,
            "activity_kind": context.item.activity_kind,
            "title": context.item.title,
            "activity_seed": context.item.activity_seed,
            "social_mode": context.item.social_mode,
            "place_key": context.item.place_key,
            "effective_snapshot": context.episode.effective_activity_snapshot,
        },
        "state_before": context.state_before,
        "previous_success": (
            {
                "beat_id": context.previous_beat.id,
                "sequence_no": context.previous_beat.sequence_no,
                "result_snapshot": context.previous_beat.result_snapshot or {},
                "post": {
                    "id": context.previous_post.id,
                    "title": _clip(context.previous_post.title, 160),
                    "body": _clip(context.previous_post.body, 1_200),
                    "topic_signature": _clip(
                        context.previous_post.topic_signature, 300
                    ),
                },
            }
            if context.previous_beat is not None and context.previous_post is not None
            else None
        ),
        "source_events": [
            {
                "source_event_id": event.source_event_id,
                "actor_world_character_id": event.actor_world_character_id,
                "excerpt": event.excerpt,
                "occurred_at": event.occurred_at.isoformat(),
                "relationship_band": event.relationship_band,
            }
            for event in context.source_events
        ],
    }


def allowed_continuity_facts(context: RoutinePostContext) -> list[str]:
    if context.previous_beat is None or context.previous_post is None:
        return []
    return [
        f"previous_beat_id:{context.previous_beat.id}",
        f"previous_post_id:{context.previous_post.id}",
        f"previous_sequence_no:{context.previous_beat.sequence_no}",
    ]


def allowed_detail_keys(context: RoutinePostContext) -> list[str]:
    keys = [
        "world.name",
        "world.tagline",
        "world.setting_description",
        "world.daily_life_description",
        "world.tone_tags",
        "character.name",
        "character.persona_summary",
        "character.speech_style",
        "character.world_local_profile",
        "character.community_profile",
        "activity.daypart",
        "activity.activity_kind",
        "activity.title",
        "activity.activity_seed",
        "activity.social_mode",
        "activity.place_key",
        "state_before",
    ]
    if context.previous_post is not None:
        keys.extend(
            [
                "previous_success.post.title",
                "previous_success.post.body",
                "previous_success.post.topic_signature",
            ]
        )
    keys.extend(
        f"source_events.{event.source_event_id}" for event in context.source_events
    )
    return keys


def build_routine_beat_plan_response_schema(
    *,
    has_previous_success: bool,
    continuity_facts: list[str],
    considered_source_event_ids: list[str],
    detail_keys: list[str],
) -> dict[str, object]:
    """Bind creative planner output to server-owned evidence identifiers."""

    schema = deepcopy(GEMINI_ROUTINE_BEAT_PLAN_RESPONSE_SCHEMA)
    properties = schema["properties"]
    if not isinstance(properties, dict):
        raise TypeError("routine planner response properties must be an object")

    scene_kind = properties["scene_kind"]
    if not isinstance(scene_kind, dict):
        raise TypeError("routine planner scene kind schema must be an object")
    scene_kind["enum"] = (
        ["continue", "conclude"] if has_previous_success else ["start"]
    )

    def constrain_string_array(
        field: str,
        values: list[str],
        *,
        minimum: int,
        maximum: int,
    ) -> None:
        field_schema = properties[field]
        if not isinstance(field_schema, dict):
            raise TypeError(f"routine planner {field} schema must be an object")
        item_schema: dict[str, object] = {"type": "string"}
        if values:
            item_schema["enum"] = list(values)
        field_schema["items"] = item_schema
        field_schema["minItems"] = minimum
        field_schema["maxItems"] = maximum

    continuity_maximum = min(6, len(continuity_facts))
    constrain_string_array(
        "continuity_facts",
        continuity_facts,
        minimum=1 if has_previous_success else 0,
        maximum=continuity_maximum,
    )
    considered_count = len(considered_source_event_ids)
    constrain_string_array(
        "considered_source_event_ids",
        considered_source_event_ids,
        minimum=considered_count,
        maximum=considered_count,
    )
    constrain_string_array(
        "used_source_event_ids",
        considered_source_event_ids,
        minimum=0,
        maximum=min(8, considered_count),
    )
    constrain_string_array(
        "used_detail_keys",
        detail_keys,
        minimum=0,
        maximum=min(8, len(detail_keys)),
    )

    effect_list = properties["source_event_effects"]
    if not isinstance(effect_list, dict):
        raise TypeError("routine planner source effect schema must be an object")
    effect_list["minItems"] = 0
    effect_list["maxItems"] = min(8, considered_count)
    if considered_source_event_ids:
        effect_item = effect_list.get("items")
        if not isinstance(effect_item, dict):
            raise TypeError("routine planner source effect item must be an object")
        effect_properties = effect_item.get("properties")
        if not isinstance(effect_properties, dict):
            raise TypeError("routine planner source effect properties must be an object")
        source_event_id = effect_properties.get("source_event_id")
        if not isinstance(source_event_id, dict):
            raise TypeError("routine planner source event id schema must be an object")
        source_event_id["enum"] = list(considered_source_event_ids)
    return schema


def _validate_plan(
    payload: dict[str, object],
    *,
    context: RoutinePostContext,
    beat: Any,
) -> schemas.RoutineBeatPlan:
    plan = schemas.RoutineBeatPlan.model_validate(payload)
    has_previous_success = (
        context.previous_beat is not None and context.previous_post is not None
    )
    if (
        plan.episode_id != context.episode.id
        or plan.beat_id != beat.id
        or plan.sequence_no != beat.sequence_no
    ):
        raise ValueError("routine beat identity mismatch")
    if not has_previous_success and plan.scene_kind != "start":
        raise ValueError("routine without prior success must start the scene")
    if has_previous_success and plan.scene_kind == "start":
        raise ValueError("continuation routine beat cannot restart the scene")
    allowed_continuity = allowed_continuity_facts(context)
    if not has_previous_success and plan.continuity_facts:
        raise ValueError("routine without prior success cannot claim continuity")
    expected_events = context.considered_source_event_ids
    if plan.considered_source_event_ids != expected_events:
        raise ValueError("considered source events must exactly match server context")
    if has_previous_success and not plan.continuity_facts:
        raise ValueError("continuation routine beat requires continuity facts")
    if not set(plan.continuity_facts).issubset(allowed_continuity):
        raise ValueError("continuity facts must reference server evidence")
    if not set(plan.used_detail_keys).issubset(allowed_detail_keys(context)):
        raise ValueError("used detail keys must reference server context")
    return plan


def _state_after(
    current: dict[str, object], plan: schemas.RoutineBeatPlan
) -> dict[str, object]:
    changes = [effect.state_change.model_dump() for effect in plan.source_event_effects]
    return activity_state_contracts.apply_state_changes(
        current,
        changes,
        scheduled_without_source=not bool(plan.used_source_event_ids),
    )


def validate_routine_generation(
    generation: RoutineGeneration,
    *,
    context: RoutinePostContext,
    beat: Any,
) -> RoutineGeneration:
    plan = _validate_plan(
        generation.plan.model_dump(mode="json"),
        context=context,
        beat=beat,
    )
    draft = schemas.RoutinePostDraft.model_validate(
        generation.draft.model_dump(mode="json")
    )
    expected_state = _state_after(context.state_before, plan)
    if generation.state_after != expected_state:
        raise ValueError("routine state must be derived from validated effects")
    return RoutineGeneration(plan=plan, draft=draft, state_after=expected_state)
