import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_next_config_defines_csp_and_clickjacking_headers() -> None:
    source = (REPO_ROOT / "frontend" / "next.config.ts").read_text(
        encoding="utf-8"
    )
    double_quoted_literals = set(
        re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', source)
    )

    assert "async headers()" in source
    assert 'source: "/:path*"' in source
    assert 'key: "Content-Security-Policy"' in source
    assert "frame-ancestors 'none'" in source
    assert "object-src 'none'" in source
    assert "base-uri 'self'" in source
    required_external_origins = {
        "https://accounts.google.com",
        "https://challenges.cloudflare.com",
    }
    assert not required_external_origins.difference(double_quoted_literals)
    assert 'process.env.NODE_ENV === "development"' in source
    assert 'developmentScriptSources' in source
    assert '["\'unsafe-eval\'"] : []' in source
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
        REPO_ROOT / "frontend" / "src" / "lib" / "community.ts"
    ).read_text(encoding="utf-8")

    assert not legacy_route.exists()
    assert "fetch(`/api/backend${path}`" in community_client
    assert "/api/community" not in community_client
