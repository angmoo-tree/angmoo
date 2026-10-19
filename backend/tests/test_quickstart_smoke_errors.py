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


@pytest.mark.parametrize("confirmed", [True, False])
@pytest.mark.parametrize("via_frontend", [True, False])
def test_environment_is_confirmed_through_protected_http_before_content(monkeypatch, confirmed, via_frontend):
    module = smoke_module()
    frontend = "http://127.0.0.1:3000"
    monkeypatch.setenv("ANGMOO_FRONTEND_ORIGIN", frontend)
    def request(base_url, path, **kwargs):
        assert base_url == (frontend if via_frontend else "http://127.0.0.1:8080")
        assert path == ("/api/backend/auth/local/environment" if via_frontend else "/api/v1/auth/local/environment")
        assert kwargs["method"] == "POST"
        assert kwargs["cookie"] == "angmoo_browser_session=synthetic-token"
        assert kwargs["origin"] == "http://127.0.0.1:3000"
        assert kwargs["local_frontend_origin"] == (None if via_frontend else frontend)
        assert kwargs["payload"]["expected_revision"] == 0
        return 200, {"confirmed_at": "2026-10-19T00:00:00Z" if confirmed else None,
                     "preferred_language": "en-US", "timezone": "UTC"}
    monkeypatch.setattr(module, "_request", request)
    if confirmed:
        module._confirm_local_environment("http://127.0.0.1:8080", token="synthetic-token", frontend_url=frontend if via_frontend else None)
    else:
        with pytest.raises(module.SmokeError, match="not confirmed"):
            module._confirm_local_environment("http://127.0.0.1:8080", token="synthetic-token", frontend_url=frontend if via_frontend else None)


def test_container_confirmation_requires_its_configured_frontend_origin(monkeypatch):
    module = smoke_module()
    monkeypatch.delenv("ANGMOO_FRONTEND_ORIGIN", raising=False)
    with pytest.raises(module.SmokeError, match="requires a frontend origin"):
        module._confirm_local_environment("http://127.0.0.1:8080", token="synthetic-token", frontend_url=None)
