"""DB failures must not claim that an AI provider failed or disclose SQL."""
import json
from types import SimpleNamespace

from sqlalchemy.exc import OperationalError
from psycopg.errors import SerializationFailure
from app.core.postgresql_concurrency import PostgresCommitOutcomeUnknown, PostgresDeadlineExceeded
from app.domains.chat.contracts.generation_lifecycle import ResponseTerminalReason
from app.domains.chat.service.response_workflow import _classify_failure, _safe_failure_facts


def test_database_abort_has_storage_reason_and_content_free_facts():
    error=OperationalError('select secret_body',{'api_key':'private-value'},SerializationFailure('private-result'))
    failure,retryable,reason=_classify_failure(error)
    assert (failure,retryable,reason)==('storage_unavailable',True,ResponseTerminalReason.COMMIT_CONFLICT)
    facts=_safe_failure_facts(error)
    assert facts['error_class']=='OperationalError' and facts['sqlstate']=='40001'
    serialized=json.dumps(facts)
    assert all(value not in serialized for value in ('secret_body','api_key','private-value','private-result'))


def test_uncertain_commit_is_not_a_retryable_provider_failure():
    assert _classify_failure(PostgresCommitOutcomeUnknown('private')) == (
        'storage_commit_uncertain',False,ResponseTerminalReason.COMMIT_CONFLICT)
    assert _classify_failure(PostgresDeadlineExceeded('private')) == (
        'storage_unavailable',True,ResponseTerminalReason.COMMIT_CONFLICT)


def test_only_valid_sqlstate_is_copied_from_bounded_exception_chain():
    inner=RuntimeError('secret prompt')
    inner.orig=SimpleNamespace(sqlstate='secret-key')
    outer=RuntimeError('provider body')
    outer.__cause__=inner
    inner.__cause__=outer
    assert _safe_failure_facts(outer)=={'error_class':'RuntimeError','sqlstate':None,'sites':[]}
