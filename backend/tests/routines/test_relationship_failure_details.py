from sqlalchemy.exc import OperationalError
from app.domains.relationships.contracts.social_context import SocialContextValidationError
from app.runtime.autonomous_activity.inputs import ActivityRelationshipValidationError,relationship_failure_details
from app.runtime.autonomous_activity.inputs import stale_relationship_input
import pytest

def test_relationship_guard_keeps_safe_database_reason_without_content():
    class ProviderPrivateDatabaseError(Exception):
        sqlstate='40001'
    storage=OperationalError('private SQL',{'secret':'private key'},ProviderPrivateDatabaseError('private body'))
    original=SocialContextValidationError('canonical_read_error',error_type='OperationalError')
    original.__cause__=storage
    failure=ActivityRelationshipValidationError(original.reason,lane='feed',original=original)
    failure.__cause__=original
    assert str(failure)=='activity_relationship_changed'
    assert relationship_failure_details(failure)=={'reason':'canonical_read_error','failure_scope':'lane','error_type':'OperationalError','sqlstate':'40001'}
    assert relationship_failure_details(ValueError('private')) is None

def test_relationship_guard_reports_changed_facts_separately_from_storage():
    failure=ActivityRelationshipValidationError('view_changed',lane='inbox')
    assert relationship_failure_details(failure)=={'reason':'view_changed','failure_scope':'lane'}
    failure.reason='private body with spaces';failure.error_type='unsafe: content'
    assert relationship_failure_details(failure)=={'failure_scope':'lane'}


@pytest.mark.parametrize('lane', ['inbox', 'feed', 'routine'])
@pytest.mark.parametrize('reason', ['version_changed', 'view_changed', 'facts_changed'])
@pytest.mark.parametrize('stage', ['RecallSelected', 'DecisionDraft', 'ValidateDecision'])
def test_conclusive_prepublication_change_is_distinct_from_storage_failure(lane, reason, stage):
    error=ActivityRelationshipValidationError(reason,lane=lane)
    assert stale_relationship_input(error,lane=lane,stage=stage)
    assert not stale_relationship_input(error,lane=lane,stage='Execute')
    assert not stale_relationship_input(error,lane=lane,stage='Settle')
    assert not stale_relationship_input(error,lane='different_lane',stage=stage)
    error.error_type='OperationalError'
    assert not stale_relationship_input(error,lane=lane,stage=stage)


@pytest.mark.parametrize('reason', ['canonical_read_error','deadline_exceeded','visibility_lost','receipt_invalid'])
@pytest.mark.parametrize('stage', ['RecallSelected', 'DecisionDraft'])
def test_other_relationship_failures_remain_errors(reason, stage):
    assert not stale_relationship_input(ActivityRelationshipValidationError(reason,lane='feed'),
        lane='feed',stage=stage)
