"""Stable task identifiers for reply and post writer result matching."""

from __future__ import annotations

import re
from typing import Any

from app.domains.routines.contracts.planning_context import ClipContextText
from app.domains.routines.contracts.writer_results import (
    JsonContextBuilder,
    WriterTaskContext,
)


def _task_id_part(value: Any, *, fallback: str = "none", clip: ClipContextText) -> str:
    text = clip(value, 120).strip()
    if not text:
        text = fallback
    text = re.sub(r"\s+", "_", text)
    text = text.replace(":", "_")
    return text[:120]


def _reply_task_id(
    *, scope: str, index: int, post_id: str, clip: ClipContextText
) -> str:
    return f"reply:{scope}:{index}:{_task_id_part(post_id, fallback='post', clip=clip)}"


def _post_task_id(
    ctx: WriterTaskContext,
    writing: dict[str, Any],
    *,
    clip: ClipContextText,
    coerce_topic_arc: JsonContextBuilder,
) -> str:
    mode = _task_id_part(writing.get("mode"), fallback="post", clip=clip)
    topic_arc = coerce_topic_arc(writing.get("topic_arc"))
    if topic_arc:
        raw_key = f"{topic_arc.get('arc_id')}:{topic_arc.get('next_step_index')}"
    else:
        raw_key = (
            writing.get("feed_cue_id")
            or writing.get("topic_key")
            or writing.get("source_post_id")
            or ctx.run_id
        )
    return f"post:{mode}:{_task_id_part(raw_key, fallback=ctx.run_id, clip=clip)}"
