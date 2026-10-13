import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_next_config_defines_csp_and_clickjacking_headers() -> None:
    source = (REPO_ROOT / "frontend" / "next.config.ts").read_text(
        encoding="utf-8"
    )
    assert "async headers()" in source
    assert 'source: "/:path*"' in source
    proxy = (REPO_ROOT / "frontend/src/proxy.ts").read_text("utf-8")
    policy = (REPO_ROOT / "frontend/src/lib/security/csp.ts").read_text("utf-8")
    assert 'key: "Content-Security-Policy"' not in source  # Per-request owner only.
    assert 'randomBytes(18)' in proxy and 'headers.set("x-nonce",nonce)' in proxy
    assert 'response.headers.set("Content-Security-Policy",policy)' in proxy
    assert 'headers.set("Content-Security-Policy",policy)' in proxy
    assert 'Content-Security-Policy-Report-Only' not in proxy
    assert "private, no-store" in proxy
    assert "frame-ancestors 'none'" in policy and "object-src 'none'" in policy
    assert "base-uri 'self'" in policy and "script-src-attr 'none'" in policy
    script = next(line for line in policy.splitlines() if "`script-src " in line)
    assert "nonce-${nonce}" in script and "wasm-unsafe-eval" in script
    assert "unsafe-inline" not in script and 'development?" \'unsafe-eval\'":""' in script
    assert all(origin in policy for origin in ("https://accounts.google.com", "https://challenges.cloudflare.com"))
    assert 'key: "X-Frame-Options"' in source
    assert 'value: "DENY"' in source


def test_legacy_unbounded_character_state_proxy_is_absent() -> None:
    legacy_route = (
        REPO_ROOT
        / "frontend"
        / "src"
        / "app"
        / "api"
        / "community"
        / "characters"
        / "[characterId]"
        / "state"
        / "route.ts"
    )
    community_client = (
        REPO_ROOT / "frontend/src/features/social/api/community.ts"
    ).read_text(encoding="utf-8")

    wrapper = (REPO_ROOT / "frontend/src/lib/http/community-request.ts").read_text(encoding="utf-8")
    transport = (REPO_ROOT / "frontend/src/lib/http/api-request.ts").read_text(encoding="utf-8")

    assert not legacy_route.exists()
    assert re.search(r"from ['\"]@/lib/http/community-request['\"]", community_client)
    assert 'from "@/lib/http/api-request"' in wrapper
    assert "return sendRequest<T>(path," in wrapper
    assert "runtimeFetch(`/api/backend${path}`" in transport
    assert "/api/community" not in community_client
