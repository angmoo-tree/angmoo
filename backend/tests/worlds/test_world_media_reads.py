"""Stored image URLs must deliver pixels under the current World read policy."""
import base64
from datetime import datetime, timezone
from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy.orm import Session

from app.config import settings
from app.core.public_media import mount_public_media
from app.domains.worlds.router import legacy_media_router
from model_fixture_support import models
from worlds.test_creator_routes import _app, _payload, _request, _user


def pixels(size=(768, 768)):
    stream = BytesIO()
    Image.new("RGB", size, (71, 102, 130)).save(stream, format="PNG")
    return base64.b64encode(stream.getvalue()).decode()


@pytest.fixture
def stack(tmp_path, monkeypatch, deny_external_network):
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path))
    app, engine, principal = _app()
    app.include_router(legacy_media_router)
    mount_public_media(app)
    owner, member, outsider = (_user(name) for name in ("image-owner", "image-member", "image-outsider"))
    with Session(engine, expire_on_commit=False) as db:
        db.add_all([owner, member, outsider]); db.commit()
    principal["user"] = owner
    world = _request(app, "POST", "/api/v1/worlds", json=_payload(visibility="private")).json()["world"]
    with Session(engine) as db:
        db.add(models.WorldMembership(id="image-member-link", world_id=world["id"], user_id=member.id,
            role="member", status="active", joined_at=datetime.now(timezone.utc))); db.commit()
    try:
        yield app, engine, principal, world, owner, member, outsider, tmp_path
    finally:
        engine.dispose()


def upload(stack, kind="icon"):
    app, engine, principal, world, owner, *_ = stack
    principal["user"] = owner
    with Session(engine) as db:
        version = db.get(models.World, world["id"]).row_version
    response = _request(app, "POST", f"/api/v1/worlds/{world['id']}/{kind}", json={
        "row_version": version, "content_type": "image/png", "data_base64": pixels((768, 768) if kind == "icon" else (1024, 384)), "alt_text": "fixture",
    })
    assert response.status_code == 200
    saved = response.json()["world"]
    return saved[f"{kind}_media_id"], saved["row_version"]


def api_url(url):
    _, _, _, world_id, name = url.split("/")
    return f"/api/v1/worlds/{world_id}/media/{name}"


@pytest.mark.parametrize("kind,size", [("icon", (768, 768)), ("banner", (1024, 384))])
def test_upload_returned_url_and_authenticated_api_deliver_same_pixels(stack, kind, size):
    app, engine, _, world, *_, root = stack
    url, version = upload(stack, kind)
    stored = root / url.removeprefix("/media/")
    for path in (url, api_url(url)):
        response = _request(app, "GET", path)
        assert response.status_code == 200
        assert response.content == stored.read_bytes()
        assert response.headers["content-type"] == "image/webp"
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert Image.open(BytesIO(response.content)).size == size
    with Session(engine) as db:
        row = db.get(models.World, world["id"])
        assert row.row_version == version and getattr(row, f"{kind}_media_id") == url


@pytest.mark.parametrize("status,visibility,viewer,expected", [
    ("draft", "private", "member", 200), ("draft", "private", "outsider", 404),
    ("draft", "public", "anonymous", 404), ("published", "private", "member", 200),
    ("published", "private", "anonymous", 404), ("published", "public", "anonymous", 200),
    ("published", "unlisted", "anonymous", 200), ("archived", "public", "anonymous", 404),
    ("archived", "private", "member", 200),
])
def test_image_read_follows_existing_world_visibility_and_membership(stack, status, visibility, viewer, expected):
    app, engine, principal, world, owner, member, outsider, _ = stack
    url, _ = upload(stack)
    with Session(engine) as db:
        row = db.get(models.World, world["id"]); row.status, row.visibility = status, visibility; db.commit()
    principal["user"] = {"member": member, "outsider": outsider, "anonymous": None}[viewer]
    assert _request(app, "GET", url).status_code == expected
    assert _request(app, "GET", api_url(url)).status_code == expected


def test_same_url_rechecks_private_transition_and_revoked_membership(stack):
    app, engine, principal, world, _, member, _, _ = stack
    url, _ = upload(stack)
    with Session(engine) as db:
        row = db.get(models.World, world["id"]); row.status, row.visibility = "published", "public"; db.commit()
    principal["user"] = None
    assert _request(app, "GET", url).status_code == 200
    with Session(engine) as db:
        db.get(models.World, world["id"]).visibility = "private"; db.commit()
    assert _request(app, "GET", url).status_code == 404
    principal["user"] = member
    assert _request(app, "GET", url).status_code == 200
    with Session(engine) as db:
        db.get(models.WorldMembership, "image-member-link").status = "left"; db.commit()
    assert _request(app, "GET", api_url(url)).status_code == 404


def test_old_current_link_or_arbitrary_file_never_grants_access(stack):
    app, _, _, world, *_, root = stack
    old, _ = upload(stack)
    fresh, version = upload(stack)
    assert old != fresh
    assert _request(app, "GET", old).status_code == 404
    arbitrary = root / "worlds" / world["id"] / "unlinked.webp"
    arbitrary.write_bytes((root / fresh.removeprefix("/media/")).read_bytes())
    assert _request(app, "GET", f"/media/worlds/{world['id']}/{arbitrary.name}").status_code == 404
    assert _request(app, "GET", fresh.replace(world["id"], "other-world")).status_code == 404
    removed = _request(app, "DELETE", f"/api/v1/worlds/{world['id']}/icon", json={"row_version": version})
    assert removed.status_code == 200
    assert _request(app, "GET", api_url(fresh)).status_code == 404


def test_existing_file_reference_requires_no_migration_or_reupload(stack):
    app, engine, _, world, *_, root = stack
    url, version = upload(stack)
    file = root / url.removeprefix("/media/")
    legacy = file.with_name("banner-existing.webp"); file.rename(legacy)
    reference = f"/media/worlds/{world['id']}/{legacy.name}"
    with Session(engine) as db:
        row = db.get(models.World, world["id"]); row.icon_media_id = reference; db.commit()
    assert _request(app, "GET", reference).content == legacy.read_bytes()
    with Session(engine) as db:
        assert db.get(models.World, world["id"]).row_version == version
    legacy.unlink()
    assert _request(app, "GET", reference).status_code == 404


def test_public_mount_still_excludes_private_directories_and_traversal(stack):
    app, _, _, world, *_, root = stack
    for directory in ("private-image-assets", "drafts", "profile-candidates"):
        path = root / directory / "fixture.webp"; path.parent.mkdir(exist_ok=True); path.write_bytes(b"private")
        assert _request(app, "GET", f"/media/{directory}/fixture.webp").status_code == 404
    for name in ("%2E%2E%2Ffixture.webp", "..%5Cfixture.webp", "secret.txt"):
        assert _request(app, "GET", f"/api/v1/worlds/{world['id']}/media/{name}").status_code == 404


def test_symlink_current_reference_never_escapes_world_directory(stack):
    app, _, _, _, *_, root = stack
    url, _ = upload(stack)
    file = root / url.removeprefix("/media/")
    other = root / "private-image-assets" / "other.webp"; other.parent.mkdir(exist_ok=True); other.write_bytes(file.read_bytes())
    file.unlink()
    try:
        file.symlink_to(other)
    except OSError as exc:
        pytest.skip(f"platform does not permit symlink fixture: {exc.__class__.__name__}")
    assert _request(app, "GET", url).status_code == 404


@pytest.mark.parametrize("profile", ["full", "public"])
def test_real_app_factory_registers_both_guarded_media_paths(stack, profile):
    from app import main
    app, _, _, _, *_ = stack
    actual = main.create_app(profile=profile, prepare_media_directories=False)
    actual.dependency_overrides.update(app.dependency_overrides)
    for path in ("/media/worlds/missing-world/image.webp", "/api/v1/worlds/missing-world/media/image.webp"):
        response = _request(actual, "GET", path)
        assert response.status_code == 404 and response.json() == {"detail": "world_not_found"}
