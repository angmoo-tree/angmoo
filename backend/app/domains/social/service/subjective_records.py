"""Validate stored self-view records against their successful source actions."""

from app.domains.social.contracts.subjective_context import (
    ActionEmotionLabel, ActionMotivationKind, ActionSubjectiveContextV1,
    SubjectiveContextProvenance,
)
from app.domains.social.contracts.today_activity import TodaySocialSubjectiveRecord
from app.domains.social.service.subjective_context import subjective_context_digest
from app.domains.social.service.today_activity_values import _execution_matches, _aware


def read_subjective_records(
    repository, owner_id, world_id, subject_id, events, evidence_by_event, executions
):
    rows = repository.subjective([event.id for event in events])
    event_by_id, output = ({event.id: event for event in events}, {})
    for row in rows:
        event, evidence = (
            event_by_id.get(row.social_event_id),
            evidence_by_event.get(row.social_event_id),
        )
        execution = executions.get(row.public_action_execution_id)
        if (
            row.owner_id != owner_id
            or row.world_id != world_id
            or row.actor_world_character_id != subject_id
            or (row.invalidated_at is not None)
            or (event is None)
            or (evidence is None)
            or (event.actor_world_character_id != subject_id)
            or (event.result != "succeeded")
            or (event.invalidated_at is not None)
            or (
                evidence.public_action_execution_id
                != row.public_action_execution_id
            )
            or (not _execution_matches(execution, event))
            or (_aware(row.captured_at) > _aware(event.occurred_at))
        ):
            continue
        try:
            context = ActionSubjectiveContextV1(
                version=row.schema_version,
                motivation_kind=ActionMotivationKind(row.motivation_kind),
                motivation_text=row.motivation_text,
                emotion_label=ActionEmotionLabel(row.emotion_label),
                emotion_text=row.emotion_text,
                emotion_intensity=row.emotion_intensity,
                provenance_kind=SubjectiveContextProvenance(row.provenance_kind),
            )
            digest = subjective_context_digest(
                execution=execution,
                event=event,
                source_content_digest=evidence.content_sha256,
                context=context,
            )
        except (TypeError, ValueError):
            continue
        if row.source_digest != digest:
            continue
        output[row.social_event_id] = TodaySocialSubjectiveRecord(
            motivation_kind=context.motivation_kind.value,
            motivation_text=context.normalized_motivation_text,
            emotion_label=context.emotion_label.value,
            emotion_text=context.normalized_emotion_text,
            emotion_intensity=context.emotion_intensity,
            source_digest=digest,
        )
    return output
