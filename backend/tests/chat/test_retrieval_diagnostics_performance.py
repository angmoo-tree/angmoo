"""Opt-in deterministic fake-provider comparison, never a paid provider call."""
import asyncio
from contextlib import nullcontext
import os
from statistics import quantiles
from time import perf_counter
from unittest.mock import patch

import pytest
from app.domains.chat.models import ChatResponseRequest
from app.domains.chat.repository.response_lifecycle import SqlAlchemyResponseLifecycleRepository
from app.domains.chat.contracts.retrieval_intent import RetrievalRoute
from app.runtime.chat.generation_workflows import SqlAlchemyResponseWorkflowUnitOfWork
from test_p8_l_p_evidence_response_streaming import response_session, _request, _workflow, _Generator, _collect, _command


class DisabledContext:
    def set(self, value):
        return None

    def reset(self, token):
        pass


@pytest.mark.skipif(os.environ.get("ANGMOO_DIAGNOSTIC_BENCHMARK") != "1", reason="explicit performance run")
@pytest.mark.parametrize("route", list(RetrievalRoute))
def test_fake_route_on_off_100_requests(response_session, route):
    original = _request(response_session, route)
    response_session.commit()
    row = response_session.get(ChatResponseRequest, original.request_id)
    template = {column.name: getattr(row, column.name) for column in ChatResponseRequest.__table__.columns}
    samples = {}
    for mode in ("off", "on"):
        durations = []
        context = patch("app.domains.chat.service.response_workflow.current", DisabledContext()) if mode == "off" else nullcontext()
        with context:
            for index in range(105):
                identifier = f"bench-{mode}-{index}"
                response_session.add(ChatResponseRequest(**{**template, "request_id": identifier, "response_slot_id": identifier, "idempotency_key": identifier}))
                response_session.commit()
                record = SqlAlchemyResponseLifecycleRepository(response_session).get_request(identifier)
                generator = _Generator()
                workflow = _workflow(response_session, route, generator)
                workflow._unit_of_work = SqlAlchemyResponseWorkflowUnitOfWork(response_session)
                started = perf_counter()
                events = asyncio.run(_collect(workflow.run(_command(record))))
                elapsed = (perf_counter() - started) * 1000
                assert events[-1].event_type.value == "completed"
                assert len(generator.requests) == 1
                if index >= 5:
                    durations.append(elapsed)
        samples[mode] = quantiles(durations, n=20)[18]
    print(f"diagnostic_route={route.value} samples=100 off_p95_ms={samples['off']:.3f} on_p95_ms={samples['on']:.3f} difference_ms={samples['on']-samples['off']:.3f}")
