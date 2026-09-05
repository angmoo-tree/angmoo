"""Join the declaration policy to the action's existing transaction."""

from datetime import datetime
from sqlalchemy.orm import Session
from app.domains.social.contracts.subjective_context import ActionSubjectiveContextV1
from app.domains.social.contracts.subjective_persistence import (
    SubjectiveExecution,
    SubjectiveEvent,
)
from app.domains.social.models.subjective_context import SocialActionSubjectiveContext
from app.domains.social.service import subjective_context as service
from app.runtime.social.subjective_references import RuntimeSubjectiveReferences


def record_declared_subjective_context(
    db: Session,
    *,
    execution: SubjectiveExecution,
    event: SubjectiveEvent,
    source_post_id: str | None,
    context: ActionSubjectiveContextV1 | None,
    captured_at: datetime,
) -> SocialActionSubjectiveContext | None:
    return service.record_declared_subjective_context(
        db,
        execution=execution,
        event=event,
        source_post_id=source_post_id,
        context=context,
        captured_at=captured_at,
        references=RuntimeSubjectiveReferences(db),
    )
