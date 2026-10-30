"""Failure isolation, physical-call budgets and explicit owner recovery."""
import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
import pytest
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.domains.relationships.contracts.daily_review import validate_review_result
from app.domains.relationships.models.personalization import RelationshipReviewWork as Work
from app.domains.relationships.service.daily_review import run_review_step
from app.domains.relationships.service.review_recovery import mark_failed
from app.providers.contracts import ProviderError
from test_relationship_daily_review import seed, Provider, References
from relationships.test_review_received_recovery import setup


@pytest.mark.parametrize("bad", ["\x00", "\ud800", "valid\x00text"])
def test_unusable_storage_text_is_rejected_before_database(bad):
    with pytest.raises(ValueError, match="storage_text_invalid"):
        validate_review_result({"decision":"update", "relationship_label":"친구", "perception":bad, "memory_refs":["m"]}, partial=False, allowed_refs={"m"})


def test_valid_unicode_and_literal_escape_are_preserved():
    value={"decision":"update", "relationship_label":"친구 🙂", "perception":"Hello 한글\n\\u0000", "memory_refs":["m"]}
    assert validate_review_result(value, partial=False, allowed_refs={"m"}) == value
    assert validate_review_result({"decision":"keep", "memory_refs":[], "ignored":"\x00"}, partial=False, allowed_refs=set()) == {"decision":"keep", "memory_refs":[]}


@pytest.mark.parametrize("invalid_text", ["\x00", "\ud800"])
def test_legacy_nul_journal_is_quarantined_without_provider_or_storage_loop(tmp_path, invalid_text):
    engine, factory, world, identifier, journal = setup(tmp_path)
    provider=Provider()
    record={"lease":"old", "attempt":1, "partial":False, "allowed_refs":["review-source"],
        "result":{"decision":"update", "relationship_label":"friend", "perception":invalid_text, "memory_refs":["review-source"]}}
    journal.write(world,identifier,record)
    for _ in range(2):
        outcome=asyncio.run(run_review_step(factory,work_id=identifier,references_factory=lambda db:References(),provider_factory=lambda base:provider,journal=journal))
        assert outcome=="needs_attention"
    assert provider.calls==[] and journal.read(world,identifier) is None
    with factory() as db:
        row=db.get(Work,identifier)
        assert row.status=="failed" and row.maintenance["hold"]=="manual"
    from app.core.result_journal import ResultJournal
    rejected=ResultJournal(journal.root.parent,"relationship-review-rejected")
    assert rejected.read(world,identifier)["record"]==record
    engine.dispose()


def test_provider_transmissions_are_bounded_and_failure_is_not_automatic_retry():
    factory,identifier,_=seed(1)
    class Unavailable(Provider):
        async def review(self,*args,**kwargs):
            self.calls.append(1)
            raise ProviderError("unavailable",failure_class="provider_unavailable",provider_code=503,retryable=True)
    provider=Unavailable()
    async def run():
        return await run_review_step(factory,work_id=identifier,references_factory=lambda db:References(),provider_factory=lambda base:provider)
    assert asyncio.run(run())=="retry_pending"
    assert asyncio.run(run())=="needs_attention"
    assert asyncio.run(run())=="needs_attention"
    assert len(provider.calls)==2


def test_unclassified_timeout_requires_manual_recovery():
    factory,identifier,_=seed(1)
    class TimeoutProvider(Provider):
        async def review(self,*args,**kwargs):
            self.calls.append(1)
            raise TimeoutError()
    provider=TimeoutProvider()
    def run():return asyncio.run(run_review_step(factory,work_id=identifier,references_factory=lambda db:References(),provider_factory=lambda base:provider))
    assert run()==run()=="needs_attention"
    assert len(provider.calls)==1


def test_slot_cannot_be_stolen_from_live_process_and_releases_on_completion():
    factory,_,_=seed(1)
    from app.runtime.memory.maintenance_slot import MaintenanceSlot
    first,second=MaintenanceSlot(factory),MaintenanceSlot(factory)
    token=first.acquire("memory")
    assert token and second.acquire("relationship") is None
    first.release("wrong-token")
    assert second.acquire("relationship") is None
    first.release(token)
    other=second.acquire("relationship")
    assert other
    second.release(other)
