"""Browser codec outputs cross real ASGI/upload/storage/Post/Chat boundaries.

Generate the seven files with creator-copy-media.spec.ts in Next/static first.
Set ANGMOO_BROWSER_PHOTO_ARTIFACTS to that run's synthetic artifact directory.
Only synthetic temporary data and fake recognition/text providers are used.
"""
import asyncio
import base64
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import sqlite3
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, ImageOps
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine, select

from app.database import get_db
from app.domains.identity.dependencies import get_current_user
from app.domains.media.router import router as media_router
from app.domains.media.models import MediaAsset
from app.domains.chat.models import MessageAttachment
from app.domains.chat.schemas import WorldChatMessageCreate
from app.core.request_limits import RequestBodyLimitMiddleware
from app.runtime.media.composition import MediaRuntime
from app.runtime.social.composition import configure_social_runtime
from app.runtime.chat.image_attachments import ChatImageAttachments
from app.domains.social.models.posts import PostMedia
from image_integration.chat_support import synthetic_chat
from image_integration.test_interpretation import FakeInterpreter
from image_integration.test_chat_attachments import stream
from social.test_l3_owner_manual_social_inbox import _fixture, _seed, _owner_payload, FRONTEND_HEADERS

_ARTIFACT_PATH = os.environ.get("ANGMOO_BROWSER_PHOTO_ARTIFACTS")
pytestmark = pytest.mark.skipif(not _ARTIFACT_PATH, reason="Local browser/ASGI bridge requires explicit ANGMOO_BROWSER_PHOTO_ARTIFACTS from both browser projects")
ARTIFACTS = Path(_ARTIFACT_PATH) if _ARTIFACT_PATH else Path(".")
FILES = ["normal.jpg", "primary.heic", "large.jpg", "orientation6.jpg", "alpha.png", "mirror.jpg", "resized-alpha.png"]


def _prepared(runtime, filename):
    path = ARTIFACTS / f"prepared-{runtime}-{filename}"
    assert path.is_file(), "Run both creator-copy-media browser projects before this bridge test"
    content = path.read_bytes()
    with Image.open(BytesIO(content)) as image:
        mime = Image.MIME[image.format]
        return content, mime, ImageOps.exif_transpose(image).size


def _upload(client, content, mime, kind, scope):
    response = client.post("/api/v1/media/assets", headers=FRONTEND_HEADERS, json={
        "scope_kind": kind, "scope_id": scope, "content_type": mime,
        "data_base64": base64.b64encode(content).decode("ascii")})
    assert response.status_code == 201, response.text
    saved = response.json()
    actual = client.get(saved["url"])
    assert actual.status_code == 200 and "no-store" in actual.headers["cache-control"]
    with Image.open(BytesIO(actual.content)) as image:
        image.load()
        assert image.size == (saved["width"], saved["height"])
        with Image.open(BytesIO(content)) as original:
            expected = ImageOps.exif_transpose(original).convert("RGBA").getpixel((10, 10))
        actual_pixel = image.convert("RGBA").getpixel((10, 10))
        assert all(abs(left - right) <= 10 for left, right in zip(expected, actual_pixel))
    return saved, actual.content


@pytest.mark.parametrize("runtime", ["next", "static-export"])
@pytest.mark.parametrize("filename", FILES)
def test_prepared_photo_real_upload_storage_and_manual_post(tmp_path, runtime, filename):
    content, mime, dimensions = _prepared(runtime, filename)
    client, engine, principal = _fixture()
    try:
        _seed(engine, principal)
        media = MediaRuntime(sessionmaker(engine), SimpleNamespace(media_root_path=tmp_path), interpreter=FakeInterpreter())
        client.app.state.media_runtime = media
        client.app.include_router(media_router, prefix="/api/v1")
        client.app.add_middleware(RequestBodyLimitMiddleware)
        configure_social_runtime(client.app)
        identity = client.post("/api/v1/worlds/world-manual/owner-character", headers=FRONTEND_HEADERS, json=_owner_payload())
        assert identity.status_code == 201
        asset, actual = _upload(client, content, mime, "world", "world-manual")
        assert (asset["width"], asset["height"]) == dimensions
        created = client.post("/api/v1/worlds/world-manual/manual-social/posts",
            headers={**FRONTEND_HEADERS, "Idempotency-Key": "browser-prepared-post"},
            json={"title": "Synthetic photo", "body": "Preserved synthetic body", "attachment_asset_id": asset["id"]})
        assert created.status_code == 201, created.text
        assert created.json()["delivery"]["provider_call_count"] == 0
        with Session(engine) as db:
            assert db.get(MediaAsset, asset["id"]).state == "ready"
            assert db.scalar(select(PostMedia.asset_id).where(PostMedia.post_id == created.json()["post"]["id"])) == asset["id"]
        if filename in {"alpha.png", "resized-alpha.png"}:
            with Image.open(BytesIO(actual)) as image: assert image.convert("RGBA").getpixel((10,10))[3] == 64
    finally: client.close(); engine.dispose()


@pytest.mark.parametrize("runtime", ["next", "static-export"])
@pytest.mark.parametrize("filename", FILES)
def test_prepared_photo_real_upload_storage_and_fake_chat_analysis(tmp_path, runtime, filename):
    content, mime, dimensions = _prepared(runtime, filename)
    fake = FakeInterpreter(); chat = synthetic_chat(tmp_path, fake)
    # The old workflow fixture uses a single-thread in-memory DB. Clone only
    # synthetic rows to a file so real ASGI sync endpoints own their connections.
    target = tmp_path / "asgi-chat.db"
    chat.db.commit()
    with sqlite3.connect(target) as copy:
        chat.db.connection().connection.driver_connection.backup(copy)
    chat.db.rollback()
    engine = create_engine(f"sqlite:///{target}", connect_args={"check_same_thread": False})
    chat.db = Session(engine); chat.sessions = sessionmaker(engine)
    chat.owner = chat.db.get(type(chat.owner), chat.owner.id)
    chat.media = MediaRuntime(chat.sessions, SimpleNamespace(media_root_path=tmp_path), interpreter=fake)
    chat.generation.images = ChatImageAttachments(chat.media)
    app = FastAPI(); app.include_router(media_router, prefix="/api/v1")
    app.add_middleware(RequestBodyLimitMiddleware)
    app.state.media_runtime = chat.media
    def db_dependency():
        with chat.sessions() as db: yield db
    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_current_user] = lambda: chat.owner
    try:
        with TestClient(app, base_url="http://127.0.0.1:3000") as client:
            asset, _actual = _upload(client, content, mime, "thread", chat.thread_id)
            assert (asset["width"], asset["height"]) == dimensions
            preflight = client.get(f"/api/v1/media/assets/{asset['id']}/preflight")
            assert preflight.status_code == 200 and preflight.json()["allowed"]
            assert fake.calls == 0
            accepted = chat.generation.accept_world_message(chat.db, chat.owner, chat.world_id, chat.thread_id,
                WorldChatMessageCreate(content="Preserved synthetic text", attachment_asset_id=asset["id"], idempotency_key="browser-photo-message"))
            events = asyncio.run(stream(chat, accepted.response_request.request_id))
            assert events[-1].event_type.value == "completed"
            assert fake.calls == 1 and chat.events == ["workflow_build", "router", "crg"]
            assert chat.db.get(MessageAttachment, accepted.user_message.id).interpretation_id
            assert chat.db.get(MediaAsset, asset["id"]).state == "ready"
    finally: chat.db.close(); engine.dispose(); chat.source.close()
