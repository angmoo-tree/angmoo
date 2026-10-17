import asyncio
from datetime import UTC, datetime, timedelta
import pytest
from app.domains.chat.contracts.retrieval_intent import RetrievalContractError
from app.domains.chat.service.hybrid_canonical import HybridCanonicalService
from app.domains.chat.service.response_workflow import _classify_failure
from chat.test_hybrid_canonical_guards import command


def test_search_timeout_is_retrieval_failure_without_another_attempt():
    calls = []
    class Hybrid:
        async def execute(self, request, *, deadline):
            calls.append(request)
            raise TimeoutError("canonical_read_deadline")
    now = datetime.now(UTC)
    with pytest.raises(RetrievalContractError, match="hybrid_retrieval_timeout") as error:
        asyncio.run(HybridCanonicalService(Hybrid()).plan_and_execute(command(), now=now,
            deadline_at=now+timedelta(seconds=60)))
    failure, retryable, reason = _classify_failure(error.value)
    assert failure == "retrieval_timeout" and retryable and reason.value == "retrieval_failure"
    assert len(calls) == 1


@pytest.mark.parametrize("error", [asyncio.CancelledError(), ValueError("source_changed"), RuntimeError("sqlite_busy")])
def test_other_failures_keep_their_type(error):
    class Hybrid:
        async def execute(self, *_args, **_kwargs): raise error
    now = datetime.now(UTC)
    with pytest.raises(type(error)) as caught:
        asyncio.run(HybridCanonicalService(Hybrid()).plan_and_execute(command(), now=now,
            deadline_at=now+timedelta(seconds=60)))
    assert caught.value is error
