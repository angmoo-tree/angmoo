"""TopicArc validation, progression, recovery, and time-continuity decisions.

The provided collaborators perform reads at their original decision points.
No Session, model, or state is copied by this service.
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from app.domains.routines.constants import APP_TIMEZONE
from app.domains.routines.contracts.topic_arcs import TopicArcContext, TopicArcWorkflows
from app.domains.routines.policies.resident_clock import (
    _aware_datetime,
    _current_kst_date,
    _event_kst_date,
    _korean_daypart_label,
)
from app.domains.routines.policies.topic_arc_roles import _validate_topic_arc_step_roles
from app.domains.routines.policies.topic_dates import (
    _CARRYOVER_ACTIVE,
    _CARRYOVER_COMPLETED,
    _CARRYOVER_DUE_TODAY,
    _CARRYOVER_EXPIRED,
    _CARRYOVER_FUTURE,
    _CARRYOVER_NONE,
    _attach_step_date_anchors,
    _carryover_phase,
    _carryover_phase_label,
    _detect_relative_date_anchor,
    _normalize_iso_date,
    _parse_target_date,
)
from app.domains.routines.schemas.resident_planning import (
    _TOPIC_ARC_SCHEMA_VERSION,
    _TopicArcDraft,
    _TopicArcPayload,
    _TopicArcStep,
)


def _topic_arc_step_dict(
    step: Any, *, workflows: TopicArcWorkflows
) -> dict[str, Any] | None:
    if isinstance(step, BaseModel):
        step = step.model_dump()
    if not isinstance(step, dict):
        return None
    role = str(step.get("role") or "").strip()
    brief = workflows.clip(step.get("brief"), 600)
    if role not in {"standalone", "setup", "development", "conclusion"} or not brief:
        return None
    result: dict[str, Any] = {"role": role, "brief": brief}
    target_date = _normalize_iso_date(step.get("target_date"))
    if target_date:
        result["target_date"] = target_date
    relative_time_original = workflows.clip(step.get("relative_time_original"), 24)
    if relative_time_original:
        result["relative_time_original"] = relative_time_original
    return result


def _carryover_time_context(
    step: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    current_date: date,
    *,
    reference_date: date | None = None,
    workflows: TopicArcWorkflows,
) -> dict[str, Any]:
    if not isinstance(step, dict):
        step = {}
    target_date = _parse_target_date(step.get("target_date"))
    relative_time_original = (
        workflows.clip(step.get("relative_time_original"), 24) or None
    )
    legacy_relative_time = False
    inferred_target_date: date | None = None
    if target_date is None and reference_date is not None:
        legacy_anchor = _detect_relative_date_anchor(step.get("brief"), reference_date)
        if legacy_anchor and legacy_anchor.get("relative_time_original") in {
            "\ub0b4\uc77c",
            "tomorrow",
        }:
            inferred_target_date = _parse_target_date(legacy_anchor.get("target_date"))
            target_date = inferred_target_date
            relative_time_original = legacy_anchor.get("relative_time_original")
            legacy_relative_time = True
    phase = _carryover_phase(target_date, current_date)
    return {
        "phase": phase,
        "label": _carryover_phase_label(phase),
        "target_date": target_date.isoformat() if target_date else None,
        "relative_time_original": relative_time_original,
        "legacy_relative_time": legacy_relative_time,
        "inferred_target_date": (
            inferred_target_date.isoformat() if inferred_target_date else None
        ),
        "current_date": current_date.isoformat(),
        "created_kst_date": (payload or {}).get("created_kst_date"),
        "carryover_status": (payload or {}).get("carryover_status")
        or _CARRYOVER_ACTIVE,
    }


def _coerce_topic_arc_draft(
    value: Any,
    *,
    arc_source: Literal["independent", "post_seed"] = "independent",
    workflows: TopicArcWorkflows,
) -> dict[str, Any] | None:
    if isinstance(value, BaseModel):
        value = value.model_dump()
    if not isinstance(value, dict):
        return None
    try:
        draft = _TopicArcDraft.model_validate(value).model_dump()
    except ValidationError:
        return None
    steps = [
        _topic_arc_step_dict(step, workflows=workflows)
        for step in draft.get("steps", [])
    ]
    if any(step is None for step in steps):
        return None
    try:
        _validate_topic_arc_step_roles(
            [_TopicArcStep.model_validate(step) for step in steps if step is not None],
            arc_source=arc_source,
        )
    except (ValidationError, ValueError):
        return None
    sanitized_steps: list[dict[str, Any]] = []
    for step in steps:
        if step is None:
            continue
        sanitized = {
            "role": step["role"],
            "brief": step["brief"],
        }
        sanitized_steps.append(sanitized)
    return {
        "arc_title": workflows.clip(draft.get("arc_title"), 200),
        "steps": sanitized_steps,
    }


def _coerce_topic_arc_payload(
    value: Any, *, workflows: TopicArcWorkflows
) -> dict[str, Any] | None:
    if isinstance(value, BaseModel):
        value = value.model_dump()
    if not isinstance(value, dict):
        return None
    try:
        payload = _TopicArcPayload.model_validate(value).model_dump()
    except ValidationError:
        return None
    steps = [
        _topic_arc_step_dict(step, workflows=workflows)
        for step in payload.get("steps", [])
    ]
    if any(step is None for step in steps):
        return None
    payload["steps"] = [step for step in steps if step is not None]
    payload["arc_title"] = workflows.clip(payload.get("arc_title"), 200)
    payload["created_kst_date"] = _normalize_iso_date(payload.get("created_kst_date"))
    payload["carryover_status"] = payload.get("carryover_status") or _CARRYOVER_ACTIVE
    return payload


def _topic_arc_active_step(
    topic_arc: dict[str, Any], *, workflows: TopicArcWorkflows
) -> dict[str, Any] | None:
    payload = _coerce_topic_arc_payload(topic_arc, workflows=workflows)
    if not payload or payload.get("status") != "active":
        return None
    index = int(payload.get("next_step_index") or 0)
    steps = payload.get("steps", [])
    if not isinstance(steps, list) or index < 0 or index >= len(steps):
        return None
    return dict(steps[index])


def _topic_arc_completed_step_summaries(
    topic_arc: dict[str, Any], *, workflows: TopicArcWorkflows
) -> list[str]:
    payload = _coerce_topic_arc_payload(topic_arc, workflows=workflows)
    if not payload:
        return []
    next_step_index = int(payload.get("next_step_index") or 0)
    steps = payload.get("steps", [])
    if not isinstance(steps, list):
        return []
    return [
        workflows.clip(step.get("brief"), 240)
        for step in steps[:next_step_index]
        if isinstance(step, dict) and workflows.clip(step.get("brief"), 240)
    ]


def _topic_arc_for_prompt(
    topic_arc: dict[str, Any] | None,
    *,
    current_date: date | None = None,
    workflows: TopicArcWorkflows,
) -> dict[str, Any] | None:
    payload = _coerce_topic_arc_payload(topic_arc, workflows=workflows)
    if not payload:
        return None
    active_step = _topic_arc_active_step(payload, workflows=workflows)
    carryover_time_context = None
    if active_step:
        raw_context = topic_arc.get("carryover_time_context") if topic_arc else None
        if isinstance(raw_context, dict):
            carryover_time_context = raw_context
        else:
            context_date = current_date
            if context_date is None and payload.get("created_kst_date"):
                context_date = date.fromisoformat(payload["created_kst_date"])
            if context_date is not None:
                carryover_time_context = _carryover_time_context(
                    active_step, payload, context_date, workflows=workflows
                )
    return {
        "arc_id": payload.get("arc_id"),
        "arc_source": payload.get("arc_source"),
        "topic_key": payload.get("topic_key"),
        "source_post_id": payload.get("source_post_id"),
        "arc_title": payload.get("arc_title"),
        "status": payload.get("status"),
        "carryover_status": payload.get("carryover_status"),
        "created_kst_date": payload.get("created_kst_date"),
        "next_step_index": payload.get("next_step_index"),
        "step_count": len(payload.get("steps", [])),
        "active_step": active_step,
        "carryover_time_context": carryover_time_context,
        "completed_step_summaries": _topic_arc_completed_step_summaries(
            payload, workflows=workflows
        ),
    }


def _make_topic_arc_id(
    ctx: TopicArcContext,
    *,
    arc_source: str,
    topic_key: str | None,
    source_post_id: str | None,
    arc_title: str,
) -> str:
    material = "|".join(
        [
            ctx.run_id,
            ctx.character.id,
            arc_source,
            topic_key or "",
            source_post_id or "",
            arc_title,
        ]
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"arc:{ctx.run_id}:{digest}"


def _build_topic_arc_payload(
    ctx: TopicArcContext,
    *,
    draft: dict[str, Any],
    arc_source: Literal["independent", "post_seed"],
    topic_key: str | None,
    source_post_id: str | None,
    workflows: TopicArcWorkflows,
) -> dict[str, Any] | None:
    coerced = _coerce_topic_arc_draft(draft, arc_source=arc_source, workflows=workflows)
    if not coerced:
        return None
    base_date = _current_kst_date(ctx)
    payload = {
        "schema_version": _TOPIC_ARC_SCHEMA_VERSION,
        "arc_id": _make_topic_arc_id(
            ctx,
            arc_source=arc_source,
            topic_key=topic_key,
            source_post_id=source_post_id,
            arc_title=coerced["arc_title"],
        ),
        "arc_source": arc_source,
        "topic_key": topic_key,
        "source_post_id": source_post_id,
        "arc_title": coerced["arc_title"],
        "steps": _attach_step_date_anchors(coerced["steps"], base_date),
        "next_step_index": 0,
        "status": "active",
        "last_post_id": None,
        "created_kst_date": base_date.isoformat(),
        "carryover_status": _CARRYOVER_ACTIVE,
    }
    return _coerce_topic_arc_payload(payload, workflows=workflows)


def _topic_arc_recovery_decision(
    ctx: TopicArcContext,
    payload: dict[str, Any] | None,
    event: Any,
    *,
    workflows: TopicArcWorkflows,
) -> dict[str, Any]:
    payload = _coerce_topic_arc_payload(payload, workflows=workflows)
    if not payload:
        return {
            "continue": False,
            "reason": "payload_invalid",
            "carryover_time_context": None,
        }
    if payload.get("status") != "active":
        return {
            "continue": False,
            "reason": "arc_not_active",
            "carryover_time_context": None,
        }
    active_step = _topic_arc_active_step(payload, workflows=workflows)
    if not active_step:
        return {
            "continue": False,
            "reason": "active_step_missing",
            "carryover_time_context": None,
        }
    carryover_time_context = _carryover_time_context(
        active_step,
        payload,
        _current_kst_date(ctx),
        reference_date=_event_kst_date(event),
        workflows=workflows,
    )
    phase = str(carryover_time_context.get("phase") or "")
    if phase == _CARRYOVER_EXPIRED:
        return {
            "continue": False,
            "reason": "past_target_date",
            "carryover_time_context": carryover_time_context,
        }
    if phase == _CARRYOVER_FUTURE:
        return {
            "continue": False,
            "reason": "future_target_date",
            "carryover_time_context": carryover_time_context,
        }
    if phase == _CARRYOVER_DUE_TODAY:
        return {
            "continue": True,
            "reason": "due_today",
            "carryover_time_context": carryover_time_context,
        }
    continuity = _topic_arc_continuity_context(ctx, payload, workflows=workflows)
    continuity_mode = str(continuity.get("continuity_mode") or "")
    if phase == _CARRYOVER_NONE and continuity_mode in {"near", "delayed"}:
        return {
            "continue": True,
            "reason": f"continuity_{continuity_mode}",
            "carryover_time_context": carryover_time_context,
        }
    return {
        "continue": False,
        "reason": (
            "long_gap_without_due_today"
            if continuity_mode in {"overnight_or_long_gap", "unknown"}
            else "not_recoverable"
        ),
        "carryover_time_context": carryover_time_context,
    }


def _active_topic_arc(ctx: TopicArcContext) -> dict[str, Any] | None:
    # v8 keeps old writing_topic_arc rows for compatibility but no longer
    # resumes them as an active writing source. Relationship points now own
    # one-shot relationship topics.
    return None


def _writing_from_topic_arc(
    topic_arc: dict[str, Any],
    *,
    current_date: date | None = None,
    workflows: TopicArcWorkflows,
) -> dict[str, Any] | None:
    payload = _coerce_topic_arc_payload(topic_arc, workflows=workflows)
    active_step = _topic_arc_active_step(payload or {}, workflows=workflows)
    if not payload or not active_step:
        return None
    carryover_time_context = topic_arc.get("carryover_time_context")
    if not isinstance(carryover_time_context, dict):
        carryover_time_context = (
            _carryover_time_context(
                active_step, payload, current_date, workflows=workflows
            )
            if current_date is not None
            else None
        )
    return {
        "mode": "arc_continuation",
        "source_post_id": payload.get("source_post_id"),
        "topic_key": payload.get("topic_key"),
        "brief": active_step.get("brief"),
        "topic_arc": payload,
        "active_step": active_step,
        "carryover_time_context": carryover_time_context,
        "completed_step_summaries": _topic_arc_completed_step_summaries(
            payload, workflows=workflows
        ),
    }


def _attach_topic_arc_to_new_writing(
    ctx: TopicArcContext,
    writing: dict[str, Any],
    *,
    arc_source: Literal["independent", "post_seed"],
    topic_key: str | None,
    source_post_id: str | None,
    workflows: TopicArcWorkflows,
) -> dict[str, Any]:
    def _skip(reason: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "mode": "none",
            "brief": None,
            "source_post_id": source_post_id,
            "skip_reason": reason,
        }
        if topic_key:
            result["topic_key"] = topic_key
        return result

    draft = writing.get("topic_arc")
    if draft is None:
        return _skip("topic_arc_required_for_root_writing")
    topic_arc = _build_topic_arc_payload(
        ctx,
        draft=draft,
        arc_source=arc_source,
        topic_key=topic_key,
        source_post_id=source_post_id,
        workflows=workflows,
    )
    active_step = _topic_arc_active_step(topic_arc or {}, workflows=workflows)
    if not topic_arc or not active_step:
        return _skip("topic_arc_invalid_for_root_writing")
    result = dict(writing)
    result["topic_arc"] = topic_arc
    result["active_step"] = active_step
    result["completed_step_summaries"] = []
    return result


def _topic_arc_continuity_context(
    ctx: TopicArcContext, topic_arc: dict[str, Any], *, workflows: TopicArcWorkflows
) -> dict[str, Any]:
    payload = _coerce_topic_arc_payload(topic_arc, workflows=workflows)
    arc_id = payload.get("arc_id") if payload else None
    last_post_id = str(payload.get("last_post_id") or "").strip() if payload else ""
    last_post_id = last_post_id or None
    last_post_at = workflows.last_post_created_at(ctx, last_post_id)
    latest_event = workflows.latest_event(ctx, arc_id)
    latest_event_at = _aware_datetime(getattr(latest_event, "provided_at", None))
    reference_at = last_post_at or latest_event_at
    current_kst = ctx.run_started_at.astimezone(APP_TIMEZONE)
    reference_kst = reference_at.astimezone(APP_TIMEZONE) if reference_at else None
    elapsed_minutes: int | None = None
    kst_date_changed: bool | None = None
    daypart_changed: bool | None = None
    continuity_mode = "unknown"
    if reference_kst is not None:
        elapsed = current_kst - reference_kst
        elapsed_minutes = max(0, int(elapsed.total_seconds() // 60))
        kst_date_changed = current_kst.date() != reference_kst.date()
        daypart_changed = _korean_daypart_label(current_kst) != _korean_daypart_label(
            reference_kst
        )
        if kst_date_changed or elapsed_minutes > 480:
            continuity_mode = "overnight_or_long_gap"
        elif elapsed_minutes <= 120:
            continuity_mode = "near"
        else:
            continuity_mode = "delayed"
    return {
        "last_post_id": last_post_id,
        "last_post_created_at": last_post_at.isoformat() if last_post_at else None,
        "latest_arc_event_at": latest_event_at.isoformat() if latest_event_at else None,
        "elapsed_minutes": elapsed_minutes,
        "kst_date_changed": kst_date_changed,
        "daypart_changed": daypart_changed,
        "continuity_mode": continuity_mode,
    }
