from datetime import UTC, datetime
import pytest
from sqlalchemy import select
from test_relationship_daily_review import seed, run, Provider, References
from app.domains.relationships.models.personalization import RelationshipReviewWork
from app.domains.relationships.models.social import RelationshipState
from app.domains.relationships.service.daily_review import apply_review
from app.domains.relationships.contracts.daily_review import ReviewNeedsSplit


def test_modified_result_is_rejected_and_view_conflict_rebases():
    factory, root_id, state_id = seed(2)
    assert run(factory, root_id, Provider()) == 'ready'
    with factory() as db:
        root = db.get(RelationshipReviewWork, root_id)
        original = root.result
        root.result = {**original, 'relationship_label': 'tampered'}
        db.commit()
        with pytest.raises(ValueError, match='result_changed'):
            apply_review(db, work_id=root_id, references=References(), now=datetime.now(UTC))
        db.rollback()
        root.result = original
        state = db.get(RelationshipState, state_id)
        state.view_version += 1
        state.perception = '이미 다른 검토에서 갱신됨'
        db.commit()
        assert apply_review(db, work_id=root_id, references=References(), now=datetime.now(UTC)) == 'rebased'
        db.commit()
        assert root.status == 'pending'
        assert state.perception == '이미 다른 검토에서 갱신됨'


def test_provider_incomplete_splits_without_applying_partial_state():
    factory, root_id, _ = seed(4)
    class Incomplete:
        async def review(self, payload, **kwargs):
            raise ReviewNeedsSplit()
    assert run(factory, root_id, Incomplete()) == 'split_pending'
    with factory() as db:
        root = db.get(RelationshipReviewWork, root_id)
        assert root.phase == 'final'
        assert root.status == 'pending'
        parts = list(db.scalars(select(RelationshipReviewWork).where(RelationshipReviewWork.parent_id == root_id)))
        assert len(parts) == 2
        assert sum(len(p.manifest['payload']['memories']) for p in parts) == 4
