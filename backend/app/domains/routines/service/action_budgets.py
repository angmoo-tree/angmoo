"""Daily post/reply budgets, reply buckets, and conflicting unfollow actions.

Settings and scope-aware counts are read at their original decision points.
"""

from __future__ import annotations

from typing import Any

from app.domains.routines.contracts.action_planning import ActionBudgetWorkflows
from app.domains.routines.contracts.planning_context import ResidentPlanningContext
from app.domains.routines.policies.action_matching import _action_name_for_policy
from app.domains.routines.policies.writing_contract import _OWNER_FEED_CUE_MODE

_REPLY_WRITER_MAX_TASKS_PER_RUN = 9

_REPLY_WRITER_BUCKET_MAX_TASKS = 3


def _daily_action_budgets(
    ctx: ResidentPlanningContext, *, workflows: ActionBudgetWorkflows
) -> dict[str, dict[str, Any]]:
    setting = workflows.ensure_setting(ctx.db, ctx.character.id)
    raw_limits: dict[str, int | None] = {
        "reply": setting.max_comments_per_day if setting.allow_reply else 0,
        "post": setting.max_posts_per_day if setting.allow_post else 0,
    }
    allowed = set(ctx.activity_policy.allowed_actions)
    budgets: dict[str, dict[str, Any]] = {}
    for action, limit in raw_limits.items():
        cooldown_seconds = 0
        if action not in allowed:
            limit = 0
        cooldown_blocked_until = None
        if limit is None:
            budgets[action] = {
                "limit": None,
                "used_today": None,
                "remaining_before_plan": None,
                "remaining_after_trim": None,
                "cooldown_seconds": cooldown_seconds,
                "cooldown_blocked_until": (
                    cooldown_blocked_until.isoformat()
                    if cooldown_blocked_until is not None
                    else None
                ),
            }
            continue
        used_today = workflows.count_today(
            ctx.db,
            character_id=ctx.character.id,
            action=action,
            now=ctx.run_started_at,
        )
        remaining = max(0, int(limit) - int(used_today))
        budgets[action] = {
            "limit": int(limit),
            "used_today": int(used_today),
            "remaining_before_plan": remaining,
            "remaining_after_trim": remaining,
            "cooldown_seconds": cooldown_seconds,
            "cooldown_blocked_until": (
                cooldown_blocked_until.isoformat()
                if cooldown_blocked_until is not None
                else None
            ),
            "cooldown_kept_in_run": 0,
        }
    return budgets


def _post_author_character_id(
    ctx: ResidentPlanningContext,
    post_id: str | None,
    *,
    workflows: ActionBudgetWorkflows,
) -> str | None:
    source_post_id = str(post_id or "").strip()
    if not source_post_id:
        return None
    post = workflows.get_post(ctx.db, source_post_id)
    return getattr(post, "author_character_id", None) if post is not None else None


def _action_conflicts_with_unfollow_target(
    ctx: ResidentPlanningContext,
    *,
    action: dict[str, Any],
    target_character_id: str,
    scope: str,
    workflows: ActionBudgetWorkflows,
) -> bool:
    if str(action.get("target_id") or "") == target_character_id:
        return True
    if (
        str(action.get("target_type") or "") == "character"
        and str(action.get("target_id") or "") == target_character_id
    ):
        return True
    post_author_id = _post_author_character_id(
        ctx, action.get("post_id"), workflows=workflows
    )
    if post_author_id == target_character_id:
        return True
    if scope == "inbox":
        actor_id = str(action.get("actor_character_id") or "").strip()
        if actor_id == target_character_id:
            return True
    return False


def _apply_unfollow_conflict_suppression(
    ctx: ResidentPlanningContext,
    action_plan: dict[str, Any],
    *,
    workflows: ActionBudgetWorkflows,
) -> dict[str, Any]:
    relationship_actions = action_plan.get("relationship_actions")
    if not isinstance(relationship_actions, list):
        return {"applied": False, "suppressed_actions": []}
    unfollow_action = next(
        (
            action
            for action in relationship_actions
            if isinstance(action, dict) and action.get("action_type") == "unfollow"
        ),
        None,
    )
    if not isinstance(unfollow_action, dict):
        return {"applied": False, "suppressed_actions": []}
    target_id = str(unfollow_action.get("target_id") or "").strip()
    if not target_id:
        return {"applied": False, "suppressed_actions": []}
    suppressed: list[dict[str, Any]] = []
    for scope, key in (("feed", "feed_actions"), ("inbox", "inbox_actions")):
        actions = action_plan.get(key, [])
        if not isinstance(actions, list):
            action_plan[key] = []
            continue
        kept: list[dict[str, Any]] = []
        for index, action in enumerate(actions):
            if isinstance(action, dict) and _action_conflicts_with_unfollow_target(
                ctx,
                action=action,
                target_character_id=target_id,
                scope=scope,
                workflows=workflows,
            ):
                suppressed.append(
                    {
                        "scope": scope,
                        "index": index,
                        "action_type": action.get("action_type"),
                        "post_id": action.get("post_id"),
                        "target_id": action.get("target_id"),
                        "reason": "unfollow_target_conflict",
                    }
                )
                continue
            kept.append(action)
        action_plan[key] = kept
    writing = action_plan.get("writing")
    if isinstance(writing, dict) and writing.get("mode") == "post_seed":
        source_post_id = str(writing.get("source_post_id") or "").strip()
        if (
            _post_author_character_id(ctx, source_post_id, workflows=workflows)
            == target_id
        ):
            suppressed.append(
                {
                    "scope": "writing",
                    "index": 0,
                    "action_type": "post",
                    "post_id": source_post_id,
                    "target_id": target_id,
                    "reason": "unfollow_target_post_seed_conflict",
                }
            )
            action_plan["writing"] = {
                "mode": "none",
                "brief": None,
                "source_post_id": source_post_id,
                "skip_reason": "unfollow_target_conflict",
            }
    review = action_plan.get("relationship_review")
    if isinstance(review, dict):
        review["suppressed_conflicts"] = suppressed
        action_plan["relationship_review"] = review
    return {
        "applied": True,
        "target_character_id": target_id,
        "suppressed_actions": suppressed,
    }


def _trim_action_plan_to_budget(
    ctx: ResidentPlanningContext,
    action_plan: dict[str, Any],
    *,
    workflows: ActionBudgetWorkflows,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(action_plan, dict):
        return action_plan, {"actions": {}, "trimmed_actions": []}
    budgets = _daily_action_budgets(ctx, workflows=workflows)
    planned_counts: dict[str, int] = {}
    kept_counts: dict[str, int] = {}
    trimmed_actions: list[dict[str, Any]] = []

    def _append_trimmed_action(
        action: dict[str, Any],
        *,
        scope: str,
        index: int,
        action_type: str,
        reason: str,
        task_id: str | None = None,
        reply_bucket: str | None = None,
    ) -> None:
        item = {
            "scope": scope,
            "index": index,
            "action_type": action_type,
            "post_id": action.get("post_id"),
            "notification_id": action.get("notification_id"),
            "notification_type": action.get("notification_type"),
            "target_type": action.get("target_type"),
            "target_id": action.get("target_id"),
            "reason": reason,
        }
        if task_id:
            item["task_id"] = task_id
        if reply_bucket:
            item["reply_bucket"] = reply_bucket
        trimmed_actions.append(item)

    def _keep_action(action: dict[str, Any], *, scope: str, index: int) -> bool:
        action_type = _action_name_for_policy(str(action.get("action_type") or ""))
        planned_counts[action_type] = planned_counts.get(action_type, 0) + 1
        budget = budgets.get(action_type)
        if budget is None or budget.get("remaining_after_trim") is None:
            kept_counts[action_type] = kept_counts.get(action_type, 0) + 1
            return True
        remaining = int(budget.get("remaining_after_trim") or 0)
        if remaining > 0:
            budget["remaining_after_trim"] = remaining - 1
            kept_counts[action_type] = kept_counts.get(action_type, 0) + 1
            return True
        _append_trimmed_action(
            action,
            scope=scope,
            index=index,
            action_type=action_type,
            reason="action_budget_exhausted",
        )
        return False

    def _reply_bucket(scope: str, action: dict[str, Any]) -> str:
        if scope == "feed":
            return "feed_reply"
        if action.get("notification_type") == "mention":
            return "mention_notification"
        return "reply_notification"

    def _reply_entry(scope: str, index: int, action: dict[str, Any]) -> dict[str, Any]:
        post_id = str(action.get("post_id") or "").strip()
        bucket = _reply_bucket(scope, action)
        return {
            "scope": scope,
            "index": index,
            "action": action,
            "bucket": bucket,
            "task_id": workflows.reply_task_id(
                scope=scope, index=index, post_id=post_id
            ),
        }

    def _keep_reply_action(entry: dict[str, Any]) -> bool:
        action = entry["action"]
        budget = budgets.get("reply")
        if budget is None or budget.get("remaining_after_trim") is None:
            kept_counts["reply"] = kept_counts.get("reply", 0) + 1
            return True
        remaining = int(budget.get("remaining_after_trim") or 0)
        if remaining > 0:
            budget["remaining_after_trim"] = remaining - 1
            kept_counts["reply"] = kept_counts.get("reply", 0) + 1
            return True
        _append_trimmed_action(
            action,
            scope=entry["scope"],
            index=entry["index"],
            action_type="reply",
            reason="action_budget_exhausted",
            task_id=entry["task_id"],
            reply_bucket=entry["bucket"],
        )
        return False

    trimmed_plan = dict(action_plan)
    kept_action_keys: set[tuple[str, int]] = set()
    reply_entries: list[dict[str, Any]] = []
    for scope, key in (("feed", "feed_actions"), ("inbox", "inbox_actions")):
        actions = action_plan.get(key, [])
        if not isinstance(actions, list):
            trimmed_plan[key] = []
            continue
        for index, action in enumerate(actions):
            if not isinstance(action, dict):
                continue
            action_type = _action_name_for_policy(str(action.get("action_type") or ""))
            if action_type == "reply":
                reply_entries.append(_reply_entry(scope, index, action))
            elif _keep_action(action, scope=scope, index=index):
                kept_action_keys.add((scope, index))

    reply_cap_summary: dict[str, Any] = {
        "limit": _REPLY_WRITER_MAX_TASKS_PER_RUN,
        "bucket_limits": {
            "feed_reply": _REPLY_WRITER_BUCKET_MAX_TASKS,
            "reply_notification": _REPLY_WRITER_BUCKET_MAX_TASKS,
            "mention_notification": _REPLY_WRITER_BUCKET_MAX_TASKS,
        },
        "planned": 0,
        "kept": 0,
        "trimmed": 0,
        "bucket_trimmed": 0,
        "budget_trimmed": 0,
        "planned_buckets": {},
        "kept_buckets": {},
        "trimmed_task_ids": [],
    }
    planned_buckets: dict[str, int] = {}
    kept_buckets: dict[str, int] = {}
    bucket_entries: dict[str, list[dict[str, Any]]] = {
        "feed_reply": [],
        "reply_notification": [],
        "mention_notification": [],
    }
    for entry in reply_entries:
        bucket = str(entry["bucket"])
        planned_buckets[bucket] = planned_buckets.get(bucket, 0) + 1
        bucket_entries.setdefault(bucket, []).append(entry)
    planned_counts["reply"] = len(reply_entries)

    reply_cap_summary["planned"] = len(reply_entries)
    reply_cap_summary["planned_buckets"] = planned_buckets
    kept_reply_entries_by_bucket: dict[str, list[dict[str, Any]]] = {}
    cap_trimmed_count = 0
    for bucket, entries in bucket_entries.items():
        kept_for_bucket = entries[:_REPLY_WRITER_BUCKET_MAX_TASKS]
        kept_reply_entries_by_bucket[bucket] = kept_for_bucket
        for entry in entries[_REPLY_WRITER_BUCKET_MAX_TASKS:]:
            _append_trimmed_action(
                entry["action"],
                scope=entry["scope"],
                index=entry["index"],
                action_type="reply",
                reason="reply_bucket_cap_trimmed",
                task_id=entry["task_id"],
                reply_bucket=bucket,
            )
            reply_cap_summary["trimmed_task_ids"].append(entry["task_id"])
            cap_trimmed_count += 1

    for bucket in ("mention_notification", "reply_notification", "feed_reply"):
        for entry in kept_reply_entries_by_bucket.get(bucket, []):
            if _keep_reply_action(entry):
                kept_action_keys.add((entry["scope"], entry["index"]))
                kept_buckets[bucket] = kept_buckets.get(bucket, 0) + 1
            else:
                reply_cap_summary["trimmed_task_ids"].append(entry["task_id"])

    budget_trimmed_count = len(
        [
            item
            for item in trimmed_actions
            if item.get("action_type") == "reply"
            and item.get("reason") == "action_budget_exhausted"
        ]
    )
    reply_cap_summary.update(
        {
            "kept": kept_counts.get("reply", 0),
            "trimmed": max(0, len(reply_entries) - kept_counts.get("reply", 0)),
            "bucket_trimmed": cap_trimmed_count,
            "budget_trimmed": budget_trimmed_count,
            "kept_buckets": kept_buckets,
        }
    )

    for scope, key in (("feed", "feed_actions"), ("inbox", "inbox_actions")):
        actions = action_plan.get(key, [])
        if not isinstance(actions, list):
            trimmed_plan[key] = []
            continue
        trimmed_plan[key] = [
            action
            for index, action in enumerate(actions)
            if isinstance(action, dict) and (scope, index) in kept_action_keys
        ]

    relationship_actions = action_plan.get("relationship_actions", [])
    if not isinstance(relationship_actions, list):
        relationship_actions = []
    kept_relationship: list[dict[str, Any]] = []
    for index, action in enumerate(relationship_actions[:1]):
        if isinstance(action, dict) and _keep_action(
            action, scope="relationship", index=index
        ):
            kept_relationship.append(action)
    trimmed_plan["relationship_actions"] = kept_relationship

    writing = action_plan.get("writing")
    if isinstance(writing, dict) and writing.get("mode") != "none":
        action_type = "post"
        planned_counts[action_type] = planned_counts.get(action_type, 0) + 1
        budget = budgets.get(action_type)
        if budget is None or budget.get("remaining_after_trim") is None:
            kept_counts[action_type] = kept_counts.get(action_type, 0) + 1
        else:
            remaining = int(budget.get("remaining_after_trim") or 0)
            if remaining > 0:
                budget["remaining_after_trim"] = remaining - 1
                kept_counts[action_type] = kept_counts.get(action_type, 0) + 1
            else:
                trimmed_actions.append(
                    {
                        "scope": "writing",
                        "index": 0,
                        "action_type": "post",
                        "post_id": writing.get("source_post_id"),
                        "notification_id": None,
                        "target_type": None,
                        "target_id": None,
                        "reason": "action_budget_exhausted",
                    }
                )
                trimmed_plan["writing"] = {
                    "mode": "none",
                    "brief": None,
                    "source_post_id": writing.get("source_post_id"),
                    "feed_cue_id": writing.get("feed_cue_id"),
                    "skip_reason": (
                        "feed_cue_pending_post_blocked"
                        if writing.get("mode") == _OWNER_FEED_CUE_MODE
                        else "action_budget_trimmed"
                    ),
                }

    suppression_summary = _apply_unfollow_conflict_suppression(
        ctx, trimmed_plan, workflows=workflows
    )

    action_summary: dict[str, Any] = {}
    for action_type in sorted(set(planned_counts) | set(kept_counts) | set(budgets)):
        budget = budgets.get(action_type, {})
        planned = planned_counts.get(action_type, 0)
        kept = kept_counts.get(action_type, 0)
        action_summary[action_type] = {
            "planned": planned,
            "kept": kept,
            "trimmed": max(0, planned - kept),
            "limit": budget.get("limit"),
            "used_today": budget.get("used_today"),
            "remaining_before_plan": budget.get("remaining_before_plan"),
            "remaining_after_trim": budget.get("remaining_after_trim"),
            "cooldown_seconds": budget.get("cooldown_seconds"),
            "cooldown_blocked_until": budget.get("cooldown_blocked_until"),
        }
    return trimmed_plan, {
        "actions": action_summary,
        "trimmed_actions": trimmed_actions,
        "reply_task_cap": reply_cap_summary,
        "reply_task_cap_trimmed": reply_cap_summary["bucket_trimmed"],
        "relationship_conflict_suppression": suppression_summary,
    }
