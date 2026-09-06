from types import SimpleNamespace

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import object_session

from app.domains.social.contracts.subjective_context import (
    ActionEmotionLabel,
    ActionMotivationKind,
    ActionSubjectiveContextV1,
)
from app.domains.social.exceptions import SubjectiveContextPersistenceError
from app.domains.social.models.subjective_context import SocialActionSubjectiveContext
from app.domains.social.service.subjective_context import (
    record_declared_subjective_context,
)
from app.runtime.social.subjective_references import RuntimeSubjectiveReferences
from test_p8_l_r_today_sns_activity import NOW, _seed_today_activity, today_session


def _context():
    return ActionSubjectiveContextV1(
        motivation_kind=ActionMotivationKind.SELF_EXPRESSION,
        motivation_text="오늘 훈련 계획을 함께 나누고 싶어서 썼어.",
        emotion_label=ActionEmotionLabel.PROUD,
        emotion_text="준비한 내용을 보여 줄 수 있어 뿌듯했어.",
        emotion_intensity=64,
    )


def test_subjective_service_preserves_attached_flush_and_caller_rollback(today_session):
    db, fixture = today_session
    execution, social_event = _seed_today_activity(db, fixture)
    previous = db.scalar(
        select(SocialActionSubjectiveContext).where(
            SocialActionSubjectiveContext.social_event_id == social_event.id
        )
    )
    db.delete(previous)
    db.commit()
    commits = []
    event.listen(db, "after_commit", lambda session: commits.append(session))
    references = RuntimeSubjectiveReferences(db)
    assert references.db is db
    row = record_declared_subjective_context(
        db,
        execution=execution,
        event=social_event,
        source_post_id="subject-root",
        context=_context(),
        captured_at=NOW.replace(tzinfo=None),
        references=references,
    )
    assert object_session(row) is db
    assert db.get(SocialActionSubjectiveContext, row.id) is row
    assert row.public_action_execution_id == execution.id
    assert row.social_event_id == social_event.id
    assert row.provenance_kind == "declared_at_action_decision"
    assert row.captured_at == NOW
    assert commits == []
    row_id = row.id
    db.rollback()
    assert db.get(SocialActionSubjectiveContext, row_id) is None
    assert commits == []


def test_subjective_service_rejects_failed_or_mismatched_action_before_sql(
    today_session,
):
    db, fixture = today_session
    execution, social_event = _seed_today_activity(db, fixture)
    statements = []
    event.listen(
        db.bind, "before_cursor_execute", lambda *args: statements.append(args[2])
    )
    refs = RuntimeSubjectiveReferences(db)
    failed = SimpleNamespace(status="failed")
    assert (
        record_declared_subjective_context(
            db,
            execution=failed,
            event=social_event,
            source_post_id="subject-root",
            context=None,
            captured_at=NOW,
            references=refs,
        )
        is None
    )
    with pytest.raises(
        SubjectiveContextPersistenceError,
        match="subjective_context_execution_not_succeeded",
    ):
        record_declared_subjective_context(
            db,
            execution=failed,
            event=social_event,
            source_post_id="subject-root",
            context=_context(),
            captured_at=NOW,
            references=refs,
        )
    mismatch = SimpleNamespace(status="succeeded", social_event_id="different-event")
    with pytest.raises(
        SubjectiveContextPersistenceError,
        match="subjective_context_execution_event_mismatch",
    ):
        record_declared_subjective_context(
            db,
            execution=mismatch,
            event=social_event,
            source_post_id="subject-root",
            context=_context(),
            captured_at=NOW,
            references=refs,
        )
    assert statements == []
    assert len(db.new) == 0
