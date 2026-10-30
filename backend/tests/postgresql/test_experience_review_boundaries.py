"""Run historical-source/current-memory review contracts on actual PostgreSQL."""
import pytest
from sqlalchemy.orm import Session
from postgresql.test_activity_transactions import store
from memory.test_p8_l_o_memory_consolidation import _stack
from memory.test_experience_review_boundary import (
    test_actual_review_uses_summary_only_and_applies_once_without_original_or_snapshot_reads,
    test_explicit_memory_delete_after_input_preparation_still_revokes_review,
    test_compact_reduction_root_preserves_summaries_and_current_memory_guard,
    test_old_input_policy_preserves_attempts_and_only_replans_unsubmitted_work,
)


@pytest.fixture
def stack(store):
    engine,_,_=store
    with Session(engine) as db:
        scope,setting,_,memory,*_=_stack(db)
        yield db,scope,setting,memory
