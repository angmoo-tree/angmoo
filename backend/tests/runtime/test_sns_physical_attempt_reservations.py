"""Network retries retain the run's durable admission and dispatch fences."""
import asyncio
from types import SimpleNamespace

import pytest

from app.integrations import direct_llm
from runtime.test_sns_budget_transport import runtime


def fail_first_submission(monkeypatch, adapter, *, fail_index=1):
    actual = adapter.generate_json
    attempts = []
    async def generate(request):
        attempts.append(request)
        if len(attempts) == fail_index:
            raise direct_llm.DirectLlmError("503 UNAVAILABLE")
        return await actual(request)
    async def no_wait(_):
        pass
    monkeypatch.setattr(adapter, "generate_json", generate)
    monkeypatch.setattr(direct_llm.asyncio, "sleep", no_wait)
    return attempts


def test_overload_retry_reserves_every_physical_normal_attempt(monkeypatch, deny_external_network):
    async def scenario():
        db, row, provider, adapter, _, tracker = runtime(monkeypatch, responses=[{"ok": True}])
        attempts = fail_first_submission(monkeypatch, adapter)
        await provider.call(node="CombinedTargetSelector", lane="selector", system="s", payload={},
            schema={}, validator=lambda value: value, max_tokens=8192)
        db.refresh(row)
        assert len(row.result["normal_reservations"]) == len(attempts) == len(tracker.calls) == 2
        assert not row.result.get("recovery_reservations")
        db.close()
    asyncio.run(scenario())


def test_last_normal_allowance_blocks_overload_resubmission(monkeypatch, deny_external_network):
    async def scenario():
        db, row, provider, adapter, _, tracker = runtime(monkeypatch, responses=[{"ok": True}])
        row.result = {**row.result, "normal_reservations": [f"old-{index}" for index in range(9)]}
        db.commit()
        attempts = fail_first_submission(monkeypatch, adapter)
        with pytest.raises(ValueError, match="activity_recovery_exhausted"):
            await provider.call(node="CombinedTargetSelector", lane="selector", system="s", payload={},
                schema={}, validator=lambda value: value, max_tokens=8192)
        db.refresh(row)
        assert len(attempts) == len(tracker.calls) == 1
        assert len(row.result["normal_reservations"]) == 10
        assert not row.result.get("recovery_reservations")
        db.close()
    asyncio.run(scenario())


def test_overload_during_json_repair_reserves_both_recovery_attempts(monkeypatch, deny_external_network):
    async def scenario():
        db, row, provider, adapter, _, tracker = runtime(monkeypatch,
            responses=[('{"incomplete":', "MAX_TOKENS"), {"ok": True}])
        attempts = fail_first_submission(monkeypatch, adapter, fail_index=2)
        await provider.call(node="CombinedTargetSelector", lane="selector", system="s", payload={},
            schema={}, validator=lambda value: value, max_tokens=8192, recover_truncation=True)
        db.refresh(row)
        assert len(attempts) == len(tracker.calls) == 3
        assert len(row.result["normal_reservations"]) == 1
        assert len(row.result["recovery_reservations"]) == 2
        db.close()
    asyncio.run(scenario())


def test_final_guard_failure_after_reservation_has_no_dispatch_or_input_receipt(monkeypatch, deny_external_network):
    async def scenario():
        db, row, provider, adapter, _, tracker = runtime(monkeypatch)
        reserved, states, receipts = [], [], []
        actual_reserve = provider.ledger.reserve_normal
        def reserve(key):
            actual_reserve(key)
            reserved.append(key)
        monkeypatch.setattr(provider.ledger, "reserve_normal", reserve)
        async def guard(_):
            if reserved:
                raise ValueError("scope_changed_after_admission")
        delivery = SimpleNamespace(dispatched=lambda: states.append("dispatched"),
            delivered=lambda: states.append("delivered"), uncertain=lambda: states.append("uncertain"))
        with pytest.raises(ValueError, match="scope_changed_after_admission"):
            await provider.call(node="CombinedTargetSelector", lane="selector", system="s", payload={},
                schema={}, validator=lambda value: value, max_tokens=8192, delivery=delivery,
                before_provider_request=guard, on_input_receipt=receipts.append)
        assert len(reserved) == 1
        assert not states and not receipts and not adapter.requests and not tracker.calls
        db.close()
    asyncio.run(scenario())
