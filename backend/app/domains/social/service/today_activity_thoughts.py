"""Validate own stored thoughts against the exact successful activity revision."""

from dataclasses import asdict
from hashlib import sha256
import json

from app.contracts.activity_thought import ActivityThought
from app.domains.social.contracts.today_activity import TodaySocialThoughtRecord
from app.domains.social.service.activity_thought import post_thought_digest
from app.domains.social.service.today_activity_values import _execution_matches


def validated_activity_thoughts(rows, *, owner_id, world_id, subject_id,
                                events, evidence_by_event, executions, posts):
    events_by_id = {event.id: event for event in events}
    result = {}
    for row in rows:
        event = events_by_id.get(row.social_event_id)
        evidence = evidence_by_event.get(row.social_event_id)
        execution = executions.get(row.public_action_execution_id)
        if (row.owner_id != owner_id or row.world_id != world_id
            or row.actor_world_character_id != subject_id
            or event is None or event.world_id != world_id or event.actor_world_character_id != subject_id
            or event.result != "succeeded" or event.invalidated_at is not None
            or evidence is None or evidence.public_action_execution_id != row.public_action_execution_id
            or not _execution_matches(execution, event)):
            continue
        if row.source_kind == "post_revision":
            post = posts.get(row.source_post_id)
            if (post is None or post.id != evidence.source_post_id or post.world_id != world_id
                or post.author_world_character_id != subject_id or post.deleted_at is not None
                or post.report_hidden_at is not None):
                continue
            expected = post_thought_digest(post)
        elif row.source_kind == "action_event" and row.source_post_id is None:
            expected = sha256(f"{execution.signature}:{event.id}".encode()).hexdigest()
        else:
            continue
        if row.source_digest != expected:
            thought = ActivityThought(status="invalid")
        else:
            try:
                thought = ActivityThought(text=row.thought_text, status=row.status, truncated=row.truncated)
            except (TypeError, ValueError):
                thought = ActivityThought(status="invalid")
        digest = sha256(json.dumps({"id": row.id, "source": row.source_digest,
                                    "current_source": expected, "thought": asdict(thought)},
                                   ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        result[event.id] = TodaySocialThoughtRecord(thought, digest, row.id)
    return result
