from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import asyncio
import pytest

from app.core.request_limits import (
    CHARACTER_CARD_REQUEST_BODY_MAX_BYTES,
    DEFAULT_REQUEST_BODY_MAX_BYTES,
    LORE_UPLOAD_REQUEST_BODY_MAX_BYTES,
    PROFILE_MEDIA_REQUEST_BODY_MAX_BYTES,
    RequestBodyLimitMiddleware,
    WORLD_PACKAGE_UPLOAD_REQUEST_BODY_MAX_BYTES,
    request_body_limit,
)


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware)

    @app.post("/{path:path}")
    async def read_body(path: str, request: Request) -> dict[str, int]:
        return {"bytes": len(await request.body())}

    return TestClient(app)


def test_request_body_limit_classifies_large_upload_routes() -> None:
    assert request_body_limit(
        path="/api/v1/agents/drafts/draft-1/card",
        method="POST",
    ) == CHARACTER_CARD_REQUEST_BODY_MAX_BYTES
    assert request_body_limit(
        path="/api/v1/agents/drafts/draft-1/card/",
        method="POST",
    ) == CHARACTER_CARD_REQUEST_BODY_MAX_BYTES
    assert request_body_limit(
        path="/api/v1/agents/char-1/lore-sources",
        method="POST",
    ) == LORE_UPLOAD_REQUEST_BODY_MAX_BYTES
    assert request_body_limit(
        path="/api/v1/agents/drafts/draft-1/media",
        method="POST",
    ) == PROFILE_MEDIA_REQUEST_BODY_MAX_BYTES
    assert request_body_limit(
        path="/api/v1/agents/char-1/media",
        method="POST",
    ) == PROFILE_MEDIA_REQUEST_BODY_MAX_BYTES
    assert request_body_limit(
        path="/api/v1/agents/char-1/image-settings/seed",
        method="POST",
    ) == PROFILE_MEDIA_REQUEST_BODY_MAX_BYTES
    assert request_body_limit(
        path="/api/v1/world-package-imports/stage",
        method="POST",
    ) == WORLD_PACKAGE_UPLOAD_REQUEST_BODY_MAX_BYTES
    assert request_body_limit(
        path="/api/v1/posts",
        method="POST",
    ) == DEFAULT_REQUEST_BODY_MAX_BYTES
    for path, method in (
        ("/api/v1/agents/drafts/draft-1/card-source", "POST"),
        ("/api/v1/agents/drafts/draft-1/card/extra", "POST"),
        ("/api/v1/agents/drafts/draft-1/card", "PUT"),
    ):
        assert request_body_limit(path=path, method=method) == DEFAULT_REQUEST_BODY_MAX_BYTES


def test_default_body_limit_rejects_content_length_before_route() -> None:
    response = _client().post(
        "/api/v1/posts",
        content=b"x" * (DEFAULT_REQUEST_BODY_MAX_BYTES + 1),
    )

    assert response.status_code == 413
    assert response.json() == {
        "detail": "Request body exceeds the allowed limit."
    }


def test_default_body_limit_accepts_exact_boundary() -> None:
    response = _client().post(
        "/api/v1/posts",
        content=b"x" * DEFAULT_REQUEST_BODY_MAX_BYTES,
    )

    assert response.status_code == 200
    assert response.json() == {"bytes": DEFAULT_REQUEST_BODY_MAX_BYTES}


def test_card_body_limit_accepts_exact_boundary_and_rejects_extra_byte() -> None:
    card_path = "/api/v1/agents/drafts/draft-1/card"
    accepted = _client().post(card_path, content=b"x" * CHARACTER_CARD_REQUEST_BODY_MAX_BYTES)
    rejected = _client().post(card_path, content=b"x" * (CHARACTER_CARD_REQUEST_BODY_MAX_BYTES + 1))

    assert accepted.status_code == 200
    assert accepted.json() == {"bytes": CHARACTER_CARD_REQUEST_BODY_MAX_BYTES}
    assert rejected.status_code == 413
    assert rejected.json() == {"detail": "Request body exceeds the allowed limit."}


def test_card_body_limit_checks_chunked_body_without_content_length() -> None:
    card_path = "/api/v1/agents/drafts/draft-1/card"
    body = iter((b"x" * CHARACTER_CARD_REQUEST_BODY_MAX_BYTES, b"y"))
    response = _client().post(card_path, content=body, headers={"Transfer-Encoding": "chunked"})

    assert response.status_code == 413
    assert response.json() == {"detail": "Request body exceeds the allowed limit."}


@pytest.mark.parametrize("path,limit", [
    ("/api/v1/media/assets", 14 * 1024 * 1024),
    *[(f"/api/v1/worlds/world/{suffix}", PROFILE_MEDIA_REQUEST_BODY_MAX_BYTES) for suffix in (
        "icon", "banner", "my-profile/media", "world-characters/actor/profile/media")],
])
@pytest.mark.parametrize("extra", [-1, 0, 1])
@pytest.mark.parametrize("declared", [False, True])
def test_exact_photo_and_world_paths_have_bounded_header_and_real_chunk_streams(path, limit, extra, declared):
    total, replies = limit + extra, []
    chunks = [b"x" * min(512 * 1024, total - at) for at in range(0, total, 512 * 1024)]
    async def receive():
        return {"type": "http.request", "body": chunks.pop(0), "more_body": bool(chunks)}
    async def send(message): replies.append(message)
    async def target(scope, receive, send):
        received = 0
        while True:
            message = await receive(); received += len(message["body"])
            if not message["more_body"]: break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": str(received).encode()})
    headers = [(b"content-length", str(total).encode())] if declared else []
    asyncio.run(RequestBodyLimitMiddleware(target)({"type": "http", "path": path, "method": "POST", "headers": headers}, receive, send))
    assert replies[0]["status"] == (413 if extra == 1 else 200)


@pytest.mark.parametrize("path", ["/api/v1/media/assets//", "/api/v1/media/assets/extra", "/api/v1/worlds//icon",
    "/api/v1/worlds/world/banner/extra", "/api/v1/worlds/world/world-characters//profile/media"])
def test_empty_or_extra_segments_are_not_photo_exceptions(path):
    assert request_body_limit(path=path, method="POST") == DEFAULT_REQUEST_BODY_MAX_BYTES
    assert request_body_limit(path="/api/v1/media/assets", method="PUT") == DEFAULT_REQUEST_BODY_MAX_BYTES
