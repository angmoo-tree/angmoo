import importlib.util
from pathlib import Path

import pytest

from app.main import app as private_app
from app.public_main import (
    PublicRuntimeConfigurationError,
    app as public_app,
    validate_public_runtime_settings,
)
from app.core.config import settings


def _operations(app) -> set[tuple[str, str]]:
    schema = app.openapi()
    return {
        (method.upper(), path)
        for path, path_item in schema["paths"].items()
        for method in path_item
        if method.lower()
        in {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
    }


def test_public_runtime_excludes_password_signup_but_keeps_google_signup() -> None:
    operations = _operations(public_app)

    assert ("POST", "/api/v1/auth/signup") not in operations
    assert ("POST", "/api/v1/auth/google") in operations
    assert ("POST", "/api/v1/auth/google/complete") in operations


def test_private_runtime_keeps_flag_gated_password_signup_for_compatibility() -> None:
    private_operations = _operations(private_app)
    public_operations = _operations(public_app)
    if private_operations == public_operations:
        assert ("POST", "/api/v1/auth/signup") not in private_operations
        return
    assert ("POST", "/api/v1/auth/signup") in private_operations


def test_hosted_production_rejects_password_signup_even_if_flag_is_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "SIGNUP_ENABLED", True)

    assert settings.password_signup_enabled is False


def test_public_runtime_rejects_enabled_password_signup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SIGNUP_ENABLED", True)

    with pytest.raises(
        PublicRuntimeConfigurationError,
        match="SIGNUP_ENABLED must be false",
    ):
        validate_public_runtime_settings()


def test_public_environment_defaults_to_google_only_signup() -> None:
    repo_root = Path(__file__).parents[2]
    source_env = repo_root / "public" / "backend.env.example"
    exported_env = repo_root / "backend" / ".env.example"
    env_example = (source_env if source_env.exists() else exported_env).read_text(
        encoding="utf-8"
    )

    assert "SIGNUP_ENABLED=false" in env_example
    assert "SIGNUP_ENABLED=true" not in env_example


def test_public_quickstart_uses_explicit_loopback_session_bootstrap() -> None:
    repo_root = Path(__file__).parents[2]
    workflow = (
        repo_root / ".github" / "workflows" / "local-smoke.yml"
    ).read_text(encoding="utf-8")

    assert "--bootstrap-local-session" in workflow

    script_path = repo_root / "scripts" / "quickstart_smoke.py"
    spec = importlib.util.spec_from_file_location("quickstart_smoke", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    module._require_loopback_backend("http://127.0.0.1:8080")
    module._require_loopback_backend("http://localhost:8080")
    with pytest.raises(module.SmokeError, match="loopback backend"):
        module._require_loopback_backend("https://angmoo.com")


def test_public_quickstart_sends_exact_frontend_session_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = Path(__file__).parents[2]
    script_path = repo_root / "scripts" / "quickstart_smoke.py"
    spec = importlib.util.spec_from_file_location("quickstart_smoke", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    captured: dict[str, str | None] = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return b"{}"

    def fake_urlopen(request, *, timeout: int):
        captured["authorization"] = request.get_header("Authorization")
        captured["cookie"] = request.get_header("Cookie")
        captured["origin"] = request.get_header("Origin")
        captured["url"] = request.full_url
        captured["timeout"] = str(timeout)
        return Response()

    monkeypatch.setattr(module, "urlopen", fake_urlopen)

    status, body = module._request(
        "http://127.0.0.1:3000",
        "/api/backend/posts/post-001/replies",
        method="POST",
        payload={"body": "synthetic"},
        cookie="angmoo_browser_session=synthetic-token",
        origin="http://127.0.0.1:3000",
    )

    assert status == 200
    assert body == {}
    assert captured == {
        "authorization": None,
        "cookie": "angmoo_browser_session=synthetic-token",
        "origin": "http://127.0.0.1:3000",
        "url": "http://127.0.0.1:3000/api/backend/posts/post-001/replies",
        "timeout": "15",
    }
