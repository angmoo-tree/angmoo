from datetime import UTC, datetime, timedelta
import json

from app.contracts.search_diagnostics import SearchDiagnosticTrace, SearchTerminal
from app.domains.chat.service.diagnostic_capture import DiagnosticCapture
from app.domains.chat.service import diagnostic_capture as module
from test_p8_l_p_evidence_response_streaming import response_session


def test_read_pending_covers_intermediate_lifecycle_and_returns_typed_trace(response_session, monkeypatch):
    from fastapi import Response
    from app.domains.chat.schemas import DiagnosticRead
    from app.contracts.retrieval_observation import Observation, current, observe
    from app.domains.chat.contracts.retrieval_intent import RetrievalRoute
    from app.domains.chat.models import ChatResponseRequest
    from app.domains.chat.repository import retrieval_diagnostics as repository
    from app.domains.chat.router import retrieval_diagnostics as router_module
    from test_p8_l_p_evidence_response_streaming import _request

    request = _request(response_session, RetrievalRoute.CANONICAL)
    row = response_session.get(ChatResponseRequest, request.request_id)
    row.state = "response_generating"
    scope = ("owner", "world", row.thread_id)
    capture = DiagnosticCapture()
    capture.configure(scope, True)
    capture.admit(scope, request.request_id)
    monkeypatch.setattr(router_module, "capture", capture)
    observation = Observation(request_id=request.request_id, detailed=True)
    token = current.set(observation)
    try:
        observe("search_trace_summary", instrumentation_version="search-diagnostic-trace.v1", captured_at_request=True)
    finally:
        current.reset(token)
    repository.save(response_session, observation)
    response_session.commit()
    def read_result():
        result = router_module.diagnostics(Response(), request_id=request.request_id, scope=scope, db=response_session)
        return DiagnosticRead.model_validate(result).model_dump(mode="json")
    assert read_result()["detail_availability"] == "pending"
    trace = SearchDiagnosticTrace(terminals=(SearchTerminal(axis="vector", terminal_state="error",
        worker_exit_code=-15, eligible_vector_count=None),)).model_dump(mode="json")
    capture.store(scope, request.request_id, [], trace)
    data = read_result()
    assert data["detail_availability"] == "available"
    assert data["search_trace"]["terminals"][0]["worker_exit_code"] == -15
    assert data["search_trace"]["terminals"][0]["eligible_vector_count"] is None



def test_capture_expiry_admission_and_late_store_after_disable(monkeypatch):
    now = [datetime(2026,9,15,tzinfo=UTC)]
    class Clock:
        @staticmethod
        def now(tz):
            return now[0]
    monkeypatch.setattr(module, "datetime", Clock)
    capture = DiagnosticCapture()
    scope = ("owner", "world", "thread")
    capture.configure(scope, True)
    for i in range(11):
        capture.admit(scope, str(i))
    assert capture.active(scope, "9") and not capture.active(scope, "10")
    trace = SearchDiagnosticTrace(terminals=(SearchTerminal(axis="vector", terminal_state="success"),)).model_dump(mode="json")
    capture.store(scope, "9", [{"search_text": "fixture"}], trace)
    assert capture.read_full(scope, "9")["search_trace"]["version"] == "search-diagnostic-trace.v1"
    assert capture.read_full(("other", "world", "thread"), "9") is None
    capture.configure(scope, False)
    capture.configure(scope, True)
    capture.store(scope, "9", [{"search_text": "late"}], trace)
    assert capture.read(scope, "9") is None
    capture.admit(scope, "new")
    now[0] += timedelta(minutes=31)
    assert not capture.status(scope)["enabled"]
    capture.store(scope, "new", [], trace)
    assert capture.read_full(scope, "new") is not None
    now[0] += timedelta(minutes=61)
    assert capture.read_full(scope, "new") is None
    assert DiagnosticCapture().read_full(scope, "new") is None


def test_full_trace_and_old_details_share_result_and_global_limits():
    capture = DiagnosticCapture()
    trace = SearchDiagnosticTrace(terminals=(SearchTerminal(axis="vector", terminal_state="error",
        worker_exit_code=-15),)).model_dump(mode="json")
    details = [{"search_text": "한"*1500, "normalized_query": "글"*1500}]*24
    for i in range(20):
        scope = ("owner", "world", str(i))
        capture.configure(scope, True)
        capture.admit(scope, str(i))
        capture.store(scope, str(i), details, trace)
    assert len(capture._results) <= 20
    assert sum(len(r[2].encode()) for r in capture._results.values()) <= 1024*1024
    for _, _, serialized in capture._results.values():
        assert len(serialized.encode()) <= 65536
        assert json.loads(serialized)["search_trace"]["terminals"][0]["worker_exit_code"] == -15
    assert capture.read_full(("owner", "world", "0"), "0") is None
