from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "frontend" / "src"


def _read(relative_path: str) -> str:
    return (FRONTEND / relative_path).read_text(encoding="utf-8")


def test_next_proxy_forwards_only_browser_session_cookies() -> None:
    route = _read("app/api/backend/[...path]/route.ts")

    assert '"angmoo_browser_session"' in route
    assert '"angmoo_google_signup_pending"' in route
    assert "filterForwardedCookies" in route
    assert 'request.headers.get("authorization")' not in route
    assert "Authorization: authorization" not in route
    assert 'request.headers.get("origin")' in route


def test_next_proxy_forwards_idempotency_key_for_safe_mutation_replay() -> None:
    route = _read("app/api/backend/[...path]/route.ts")

    assert 'request.headers.get("idempotency-key")' in route
    assert '{ "Idempotency-Key": idempotencyKey }' in route


def test_backend_proxy_preserves_allowlisted_set_cookie_on_all_statuses() -> None:
    proxy = _read("lib/backend.ts")

    assert "getSetCookie" in proxy
    assert "forwardedResponseHeaders" in proxy
    assert 'headers.append("set-cookie"' in proxy
    bodyless = proxy.index("BODYLESS_STATUSES.has")
    headers = proxy.index("forwardedResponseHeaders")
    assert headers < bodyless


def test_browser_auth_storage_contains_no_session_or_pending_token() -> None:
    agents = _read("lib/agents.ts")

    assert "angmoo.authToken" not in agents
    assert "pending_token" not in agents
    assert "getStoredToken" not in agents
    assert "hasStoredAuth" not in agents
    assert "Authorization: `Bearer" not in agents
    assert 'credentials: "same-origin"' in agents


def test_browser_auth_provider_bootstraps_from_auth_me() -> None:
    provider = _read("components/auth-provider.tsx")
    layout = _read("app/layout.tsx")

    assert 'type AuthStatus = "checking" | "authenticated" | "unauthenticated"' in provider
    assert "getMe" in provider
    assert "useAuth" in provider
    assert "<AuthProvider>" in layout


def test_community_and_tree_clients_do_not_create_user_bearer_headers() -> None:
    for relative_path in ("lib/community.ts", "lib/tree.ts"):
        source = _read(relative_path)
        assert "getStoredToken" not in source
        assert "Authorization: `Bearer" not in source
        assert '"same-origin"' in source
