"""Apply task-keyed writer results and reject missing or copied public output."""

from __future__ import annotations
from typing import Any
import re


def _reply_task_results_by_id(writing: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    raw_results = (
        writing.get("reply_task_results", []) if isinstance(writing, dict) else []
    )
    if not isinstance(raw_results, list):
        return results
    for item in raw_results:
        if isinstance(item, dict):
            task_id = str(item.get("task_id") or "").strip()
            if task_id:
                results[task_id] = item
    return results


def _reply_tasks_by_id(tasks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(task.get("task_id")): task
        for task in tasks
        if isinstance(task, dict) and task.get("task_id")
    }


def _missing_reply_task_ids(
    writing: dict[str, Any], tasks: list[dict[str, Any]]
) -> list[str]:
    results = _reply_task_results_by_id(writing)
    missing: list[str] = []
    for task in tasks:
        task_id = str(task.get("task_id") or "")
        result = results.get(task_id)
        if not result or not str(result.get("body") or "").strip():
            missing.append(task_id)
    return missing


def _required_handle_text(post_task: dict[str, Any] | None) -> str | None:
    if not isinstance(post_task, dict) or not post_task.get("mention_required"):
        return None
    handle = str(post_task.get("mention_target_handle") or "").strip()
    if not handle:
        return None
    return handle if handle.startswith("@") else f"@{handle}"


def _post_body_missing_required_mention(
    post_task: dict[str, Any] | None, body: str
) -> bool:
    required = _required_handle_text(post_task)
    if not required:
        return False
    return required.lower() not in body.lower()


def _post_body_has_forbidden_structure_label(body: str) -> bool:
    return bool(
        re.search(
            r"(^|\s)(발단|전개|결말|setup|development|conclusion)\s*[:：]",
            body,
            flags=re.IGNORECASE,
        )
    )


def _source_copy_windows(source: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", source or "").strip()
    if len(normalized) < 40:
        return []
    windows: list[str] = []
    for index in range(0, max(1, len(normalized) - 39), 40):
        window = normalized[index : index + 60].strip()
        if len(window) >= 40:
            windows.append(window)
        if len(windows) >= 4:
            break
    return windows


def _post_body_copies_source(post_task: dict[str, Any] | None, body: str) -> bool:
    if not isinstance(post_task, dict):
        return False
    sources: list[str] = []
    source_body = str(post_task.get("source_body") or "").strip()
    if source_body:
        sources.append(source_body)
    seed = post_task.get("selected_feed_seed")
    if isinstance(seed, dict):
        for key in ("source_body", "seed_brief"):
            text = str(seed.get(key) or "").strip()
            if text:
                sources.append(text)
    normalized_body = re.sub(r"\s+", " ", body or "").strip()
    return any(
        window and window in normalized_body
        for source in sources
        for window in _source_copy_windows(source)
    )


def _post_task_needs_repair(
    writing: dict[str, Any], post_task: dict[str, Any] | None
) -> bool:
    if not isinstance(post_task, dict):
        return False
    result = writing.get("post_task_result") if isinstance(writing, dict) else None
    if not isinstance(result, dict) or result.get("task_id") != post_task.get(
        "task_id"
    ):
        return True
    title = str(result.get("post_title") or "").strip()
    body = str(result.get("post_body") or "").strip()
    if not title or not body:
        return True
    if _post_body_missing_required_mention(post_task, body):
        return True
    if _post_body_has_forbidden_structure_label(body):
        return True
    if _post_body_copies_source(post_task, body):
        return True
    return False


def _write_task_summary(
    write_tasks: dict[str, Any],
    writing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    writing = writing if isinstance(writing, dict) else {}
    reply_tasks = (
        write_tasks.get("reply_tasks", []) if isinstance(write_tasks, dict) else []
    )
    if not isinstance(reply_tasks, list):
        reply_tasks = []
    post_task = write_tasks.get("post_task") if isinstance(write_tasks, dict) else None
    reply_results = _reply_task_results_by_id(writing)
    reply_written = [
        task_id
        for task_id, result in reply_results.items()
        if str(result.get("body") or "").strip()
    ]
    reply_repaired = [
        task_id
        for task_id, result in reply_results.items()
        if result.get("repair_attempted") and str(result.get("body") or "").strip()
    ]
    post_result = writing.get("post_task_result") if isinstance(writing, dict) else None
    post_written = bool(
        isinstance(post_result, dict)
        and str(post_result.get("post_title") or "").strip()
        and str(post_result.get("post_body") or "").strip()
    )
    topic_arc = None
    if isinstance(post_task, dict):
        topic_arc = post_task.get("topic_arc")
    return {
        "reply_task_count": len(reply_tasks),
        "reply_written_count": len(reply_written),
        "reply_repaired_count": len(reply_repaired),
        "reply_missing_count": max(0, len(reply_tasks) - len(reply_written)),
        "post_task_required": isinstance(post_task, dict),
        "post_task_mode": post_task.get("mode")
        if isinstance(post_task, dict)
        else None,
        "topic_arc": topic_arc,
        "post_written": post_written,
        "post_repaired": bool(
            isinstance(post_result, dict)
            and post_result.get("repair_attempted")
            and post_written
        ),
    }


def _mandatory_post_missing_reason(
    writing: dict[str, Any],
    action_budget_trim_summary: dict[str, Any] | None,
) -> str | None:
    reason = str(writing.get("skip_reason") or "").strip()
    if reason:
        return reason
    if isinstance(action_budget_trim_summary, dict):
        for item in action_budget_trim_summary.get("trimmed_actions", []):
            if (
                isinstance(item, dict)
                and item.get("scope") == "writing"
                and item.get("action_type") == "post"
            ):
                return str(item.get("reason") or "action_budget_trimmed")
    mode = str(writing.get("mode") or "").strip()
    return f"missing_post_task_for_mode_{mode or 'unknown'}"


def _apply_reply_writer_output(
    writing: dict[str, Any],
    reply_tasks: list[dict[str, Any]],
    output: dict[str, Any],
    *,
    repair_attempted: bool,
    writer_node: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = dict(writing) if isinstance(writing, dict) else {}
    task_by_id = _reply_tasks_by_id(reply_tasks)
    existing = _reply_task_results_by_id(result)
    replies = output.get("replies", []) if isinstance(output, dict) else []
    if not isinstance(replies, list):
        replies = []
    for item in replies:
        if not isinstance(item, dict):
            continue
        task_id = str(item.get("task_id") or "").strip()
        task = task_by_id.get(task_id)
        body = str(item.get("body") or "").strip()
        if task is None or not body:
            continue
        proposal = task.get("activity_proposal")
        proposal_response = None
        if isinstance(proposal, dict):
            decision = str(item.get("proposal_decision") or "").strip()
            if decision not in {"accept", "reject", "counter"}:
                continue
            proposal_response = {
                "proposal_id": proposal.get("proposal_id"),
                "decision": decision,
                "counter_activity_seed": item.get("counter_activity_seed"),
                "counter_place_key": item.get("counter_place_key"),
                "counter_target_daypart": item.get("counter_target_daypart"),
                "counter_date_policy": item.get("counter_date_policy"),
                "counter_target_date": item.get("counter_target_date"),
            }
        existing[task_id] = {
            "task_id": task_id,
            "scope": task.get("scope"),
            "index": task.get("action_index"),
            "post_id": task.get("target_post_id"),
            "body": body,
            "writer_node": writer_node,
            "repair_attempted": repair_attempted,
            "repair_succeeded": repair_attempted,
            "proposal_response": proposal_response,
        }
    ordered_results = [
        existing[task["task_id"]]
        for task in reply_tasks
        if task.get("task_id") in existing
    ]
    result["reply_task_results"] = ordered_results
    result["reply_bodies"] = [
        {
            "scope": item.get("scope"),
            "index": item.get("index"),
            "post_id": item.get("post_id"),
            "body": item.get("body"),
            "task_id": item.get("task_id"),
            "proposal_response": item.get("proposal_response"),
        }
        for item in ordered_results
        if str(item.get("body") or "").strip()
    ]
    missing = _missing_reply_task_ids(result, reply_tasks)
    writer_result = {
        "writer_node": writer_node,
        "task_count": len(reply_tasks),
        "written_task_ids": [
            item.get("task_id")
            for item in ordered_results
            if str(item.get("body") or "").strip()
        ],
        "missing_task_ids": missing,
        "repair_attempted": repair_attempted,
    }
    return result, writer_result
