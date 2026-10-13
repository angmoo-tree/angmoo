"""Focused unchanged World media HTTP authorization, CAS and archive boundaries."""
import base64
from datetime import datetime, timezone
from io import BytesIO
import pytest
from PIL import Image
from sqlalchemy.orm import Session
from model_fixture_support import models
from app.config import settings
from worlds.test_creator_routes import _app, _payload, _request, _user


@pytest.mark.parametrize("kind", ["icon", "banner"])
def test_world_media_owner_only_stable_conflict_and_archived_guard(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path))
    app, engine, principal = _app()
    owner, member = _user("media-owner"), _user("media-member")
    with Session(engine, expire_on_commit=False) as db:
        db.add_all([owner, member]); db.commit()
    principal["user"] = owner
    created = _request(app, "POST", "/api/v1/worlds", json=_payload()).json()["world"]
    world_id = created["id"]
    with Session(engine) as db:
        db.add(models.WorldMembership(id="media-member-link", world_id=world_id, user_id=member.id,
            role="member", status="active", joined_at=datetime.now(timezone.utc))); db.commit()
    stream = BytesIO(); Image.new("RGB", (320, 120), (80, 90, 120)).save(stream, format="PNG")
    upload = {"row_version": created["row_version"], "content_type": "image/png",
        "data_base64": base64.b64encode(stream.getvalue()).decode(), "alt_text": "Synthetic media"}
    path = f"/api/v1/worlds/{world_id}/{kind}"
    principal["user"] = member
    assert _request(app, "POST", path, json=upload).status_code == 403
    principal["user"] = owner
    response = _request(app, "POST", path, json=upload)
    assert response.status_code == 200
    saved = response.json()["world"]
    url = saved[f"{kind}_media_id"]
    stored = tmp_path / url.removeprefix("/media/")
    content = stored.read_bytes()
    conflict = _request(app, "POST", path, json=upload)
    assert conflict.status_code == 409
    assert stored.read_bytes() == content
    with Session(engine) as db:
        row = db.get(models.World, world_id)
        assert row.row_version == saved["row_version"] and getattr(row, f"{kind}_media_id") == url
        row.status = "archived"; db.commit()
    archived = _request(app, "DELETE", path, json={"row_version": saved["row_version"]})
    assert archived.status_code == 409
    assert stored.read_bytes() == content
    engine.dispose()
