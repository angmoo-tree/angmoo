"""The current registration smoke must not accept unrelated HTTP failures."""
import importlib.util
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

import pytest


def smoke_module():
    path = Path(__file__).resolve().parents[2] / "scripts/quickstart_smoke.py"
    spec = importlib.util.spec_from_file_location("current_quickstart_smoke", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("actual", [401, 403, 422, 500])
def test_explicit_conflict_expectation_keeps_other_http_failures_fatal(monkeypatch, actual):
    module = smoke_module()
    def reject(request, timeout):
        raise HTTPError(request.full_url, actual, "fixture", {}, BytesIO(b'{"detail":"fixture"}'))
    monkeypatch.setattr(module, "urlopen", reject)
    with pytest.raises(module.SmokeError, match=f"returned {actual}"):
        module._request("http://127.0.0.1", "/api/v1/agents/fixture/local-key",
                        method="POST", payload={}, expected_error_status=409)


def test_specific_denial_is_returned_for_the_callers_exact_status_check(monkeypatch):
    module = smoke_module()
    def reject(request, timeout):
        raise HTTPError(request.full_url, 409, "fixture", {}, BytesIO(b'{"detail":"legacy_local_only"}'))
    monkeypatch.setattr(module, "urlopen", reject)
    assert module._request("http://127.0.0.1", "/api/v1/agents/fixture/local-key",
                           method="POST", payload={}, expected_error_status=409) == (409, {"detail": "legacy_local_only"})
