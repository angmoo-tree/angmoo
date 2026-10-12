"""Strict own-profile input through upload, version guards and real pixel GET."""
import base64
from io import BytesIO

from PIL import Image
import pytest

from app.config import settings
from app.core.public_media import mount_public_media
from world_characters.test_owner_identity import _fixture, _seed_world, FRONTEND_HEADERS


@pytest.mark.parametrize("kind,size", [("avatar", (768, 768)), ("banner", (1024, 384))])
def test_my_profile_exact_payload_upload_and_get_preserve_validation(tmp_path, monkeypatch, deny_external_network, kind, size):
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path))
    client, engine, principal = _fixture()
    try:
        _, outsider = _seed_world(engine, principal)
        mount_public_media(client.app)
        context = client.post("/api/v1/worlds/world-a/my-profile/ensure", headers=FRONTEND_HEADERS).json()
        stream = BytesIO(); Image.new("RGB", size, (61, 88, 101)).save(stream, format="PNG")
        body = {"version": context["version"], "media_type": kind, "content_type": "image/png",
            "data_base64": base64.b64encode(stream.getvalue()).decode()}
        path = "/api/v1/worlds/world-a/my-profile/media"
        rejected = client.post(path, headers=FRONTEND_HEADERS, json={**body, "filename": f"{kind}.webp"})
        assert rejected.status_code == 422
        assert any(row["loc"] == ["body", "filename"] and row["type"] == "extra_forbidden" for row in rejected.json()["detail"])
        assert not list(tmp_path.rglob("*.webp"))
        uploaded = client.post(path, headers=FRONTEND_HEADERS, json=body)
        assert uploaded.status_code == 200
        saved = uploaded.json()
        assert saved["profile"]["handle"] == context["profile"]["handle"]
        url = saved["profile"][f"{kind}_url"]
        content = client.get(url)
        assert content.status_code == 200 and content.headers["content-type"] == "image/webp"
        assert Image.open(BytesIO(content.content)).size == size
        restored = client.post("/api/v1/worlds/world-a/my-profile/ensure", headers=FRONTEND_HEADERS).json()
        assert restored["profile"][f"{kind}_url"] == url
        assert client.post(path, headers=FRONTEND_HEADERS, json=body).status_code == 409
        assert client.get(url).content == content.content
        principal["user"] = outsider
        assert client.post(path, headers=FRONTEND_HEADERS, json={**body, "version": saved["version"]}).status_code in (403, 404)
    finally:
        client.close(); engine.dispose()
