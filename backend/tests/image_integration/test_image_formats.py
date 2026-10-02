"""Real encoded pixels through provider, owned storage and received-result recovery."""
import asyncio
import base64
from copy import deepcopy
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone

import httpx
from PIL import Image, PngImagePlugin
import pytest
from sqlalchemy import select, func

from app.domains.media.contracts import InvalidProfileMediaError
from app.domains.media.generation_contracts import EffectiveReference, GenerationRequest, ImageSubmissionError, ImageResult, ImagePreparationError
from app.domains.media.models import MediaAsset
from app.domains.social.models.posts import PostMedia, PostImageGenerationJob
from app.integrations.image_api import ImageApiClient
from app.integrations.image_api import parse_image_result, prepare_api_reference
from app.integrations.media.images import inspect_image_bytes, ImageBytesError
from app.domains.media.service.assets import prepare_asset_image, AssetService
from image_integration.test_providers import CATALOG, Http
from image_integration.test_generation_lifecycle import configured, admit, OWNER, POST

FORMATS = [("PNG", "image/png", "png"), ("JPEG", "image/jpeg", "jpg"), ("WEBP", "image/webp", "webp")]
PROVIDERS = [("nanogpt", "krea-v2/turbo"), ("openrouter", "krea/krea-2-medium-turbo")]


def encoded(format, *, size=(18, 24), transparent=False, **options):
    buffer = BytesIO()
    Image.new("RGBA" if transparent else "RGB", size, (20, 40, 60, 90) if transparent else (20, 40, 60)).save(buffer, format, **options)
    return buffer.getvalue()


def request(provider, model, *, endpoint=None):
    return GenerationRequest(provider, model, "one scene", None, {}, EffectiveReference(False),
        endpoint or deepcopy(CATALOG[f"{provider}:{model}"]["payload"]["endpoints"][0]))


@pytest.mark.parametrize("provider,model", PROVIDERS)
@pytest.mark.parametrize("format,mime,extension", FORMATS)
@pytest.mark.parametrize("declaration", ["absent", None, "", "correct"])
def test_provider_detects_missing_mime_without_reencoding(provider, model, format, mime, extension, declaration):
    content = encoded(format)
    item = {"b64_json": base64.b64encode(content).decode("ascii")}
    if declaration != "absent":
        item["media_type"] = mime if declaration == "correct" else declaration
    http = Http(lambda *_: httpx.Response(200, json={"data": [item]}))
    result = asyncio.run(ImageApiClient(provider, http).generate(request(provider, model), "synthetic", None))
    assert result.content == content and result.content_type == mime
    assert len(http.calls) == 1


@pytest.mark.parametrize("format,mime,extension", FORMATS)
def test_owned_storage_and_content_read_keep_format_and_unnecessary_encoding_out(tmp_path, format, mime, extension):
    sessions, media, _ = configured(tmp_path)
    content = encoded(format)
    with sessions() as db:
        asset = media.assets.upload(db, owner_id=OWNER, scope_kind="world", scope_id="social-uow-world",
            content_type=mime, content=content, draft=False)
        db.commit()
        assert asset.storage_key.endswith("." + extension) and asset.content_type == mime
        assert (asset.width, asset.height, asset.byte_size) == (18, 24, len(content))
        assert asset.content_hash == hashlib.sha256(content).hexdigest()
        row, actual = media.assets.read(db, owner_id=OWNER, asset_id=asset.id)
        assert actual == content and row.content_type == mime
        with Image.open(BytesIO(actual)) as image:
            assert image.format == format


@pytest.mark.parametrize("format,mime,extension", FORMATS)
@pytest.mark.parametrize("fault", ["spool", "asset", "db", "attachment"])
def test_worker_received_format_recovers_without_another_provider_call(tmp_path, monkeypatch, format, mime, extension, fault):
    sessions, media, fake = configured(tmp_path)
    original_generate = fake.generate
    content = encoded(format)
    async def generate(*args, **kwargs):
        await original_generate(*args, **kwargs)
        return ImageResult(content, mime)
    fake.generate = generate
    identity = admit(sessions, media)
    target, name = {"spool": (media.worker, "_write_received"), "asset": (media.assets, "upload"),
        "db": (media.worker, "_persist_result"), "attachment": (media.worker, "_attach")}[fault]
    original = getattr(target, name)
    def fail(*args, **kwargs):
        if fault == "db":
            db = args[0]
            commit = db.commit
            db.commit = lambda: (_ for _ in ()).throw(OSError("synthetic database failure"))
            try:
                return original(*args, **kwargs)
            finally:
                db.commit = commit
        raise OSError("synthetic local failure")
    monkeypatch.setattr(target, name, fail)
    asyncio.run(media.worker.process(identity))
    with sessions() as db:
        assert db.get(PostImageGenerationJob, identity).status == ("result_ready" if fault == "attachment" else "result_pending")
        assert db.scalar(select(PostMedia)) is None
    monkeypatch.setattr(target, name, original)
    asyncio.run(media.worker.process(identity))
    asyncio.run(media.worker.process(identity))
    with sessions() as db:
        job = db.get(PostImageGenerationJob, identity)
        assert job.status == "succeeded" and fake.calls == 1
        assert db.scalar(select(func.count()).select_from(PostMedia).where(PostMedia.post_id == POST)) == 1
        asset = db.get(MediaAsset, job.result_asset_id)
        assert asset.content_type == mime and asset.storage_key.endswith("." + extension)
        assert media.assets.read(db, owner_id=OWNER, asset_id=asset.id)[1] == content


@pytest.mark.parametrize("item,stage", [
    ({"b64_json": "%%%"}, "base64"), ({"b64_json": 7}, "base64"), ({"url": "https://invalid.example/private"}, "base64"),
    ({"b64_json": "data:image/png;base64,abcd"}, "base64"),
    ({"b64_json": base64.b64encode(encoded("JPEG")).decode(), "media_type": "image/png"}, "mime"),
    ({"b64_json": base64.b64encode(encoded("PNG")).decode(), "media_type": 1}, "mime"),
    ({"b64_json": base64.b64encode(encoded("PNG")).decode(), "media_type": {"secret": "not logged"}}, "mime"),
    ({"b64_json": base64.b64encode(b"RIFFxxxxNOTP").decode()}, "format"),
    ({"b64_json": base64.b64encode(b"<svg></svg>").decode()}, "format"),
    ({"b64_json": base64.b64encode(encoded("GIF")).decode()}, "format"),
])
def test_safe_parser_stage_rejects_wrong_mime_base64_and_unobserved_contract(item, stage):
    with pytest.raises(ImageSubmissionError) as failure:
        parse_image_result(httpx.Response(200, json={"data": [item]}))
    assert str(failure.value) == "provider_image_invalid" and failure.value.stage == stage
    assert "secret" not in str(failure.value)


@pytest.mark.parametrize("body,stage", [([], "envelope"), ({}, "envelope"), ({"data": {}}, "envelope"),
    ({"data": []}, "cardinality"), ({"data": [{}, {}]}, "cardinality"), ({"data": [1]}, "envelope")])
def test_parser_validates_envelope_and_exact_cardinality(body, stage):
    with pytest.raises(ImageSubmissionError) as failure:
        parse_image_result(httpx.Response(200, json=body))
    assert failure.value.stage == stage


def test_strict_base64_length_and_decoded_limit_are_independent(monkeypatch):
    monkeypatch.setattr("app.integrations.image_api.MAX_RESULT_BYTES", 2)
    for value, stage in [("a" * 8, "base64"), (base64.b64encode(b"123").decode(), "size")]:
        with pytest.raises(ImageSubmissionError) as failure:
            parse_image_result(httpx.Response(200, json={"data": [{"b64_json": value}]}))
        assert failure.value.stage == stage
    with pytest.raises(ImageSubmissionError) as failure:
        parse_image_result(httpx.Response(200, content=b"not json"))
    assert failure.value.stage == "json"


@pytest.mark.parametrize("format", ["JPEG", "WEBP"])
def test_truncated_pixels_fail_actual_decoding(format):
    content = encoded(format, size=(128, 128))
    with pytest.raises(ImageBytesError) as failure:
        inspect_image_bytes(content[:-15], max_bytes=100000)
    assert failure.value.stage == "decode"


@pytest.mark.parametrize("format", ["PNG", "WEBP"])
def test_animation_and_geometry_remain_bounded(format):
    out = BytesIO()
    Image.new("RGB", (18, 24), "red").save(out, format, save_all=True, append_images=[Image.new("RGB", (18, 24), "blue")])
    with pytest.raises(ImageBytesError) as failure:
        inspect_image_bytes(out.getvalue(), max_bytes=100000)
    assert failure.value.stage == "frames"
    with pytest.raises(ImageBytesError) as failure:
        inspect_image_bytes(encoded(format, size=(4097, 1)), max_bytes=100000)
    assert failure.value.stage == "geometry"


@pytest.mark.parametrize("format,mime,extension", FORMATS)
def test_privacy_and_exif_cleanup_keep_format_and_apply_rotation_once(format, mime, extension):
    exif = Image.Exif(); exif[274] = 6; exif[315] = "private author"
    content = encoded(format, size=(30, 20), exif=exif)
    result = prepare_asset_image(mime, content, max_bytes=100000)
    assert result.normalized and result.info.format == format and (result.info.width, result.info.height) == (20, 30)
    with Image.open(BytesIO(result.content)) as image:
        assert not image.getexif()
    again = prepare_asset_image(mime, result.content, max_bytes=100000)
    assert not again.normalized and again.content == result.content


@pytest.mark.parametrize("format,mime,extension", [FORMATS[0], FORMATS[2]])
def test_metadata_cleanup_preserves_alpha_and_valid_color_profile(format, mime, extension):
    from PIL import ImageCms
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    exif = Image.Exif(); exif[315] = "private author"
    result = prepare_asset_image(mime, encoded(format, transparent=True, exif=exif, icc_profile=icc), max_bytes=100000)
    with Image.open(BytesIO(result.content)) as image:
        assert image.info["icc_profile"] == icc and image.convert("RGBA").getpixel((0, 0))[3] == 90
        assert not image.getexif()


def test_card_text_is_removed_without_rewriting_original_source():
    metadata = PngImagePlugin.PngInfo(); metadata.add_text("chara", "private card data"); metadata.add_itxt("note", "private note")
    original = encoded("PNG", pnginfo=metadata)
    result = prepare_asset_image("image/png", original, max_bytes=100000)
    with Image.open(BytesIO(original)) as image:
        assert image.info["chara"] == "private card data"
    with Image.open(BytesIO(result.content)) as image:
        image.load(); assert not image.text


@pytest.mark.parametrize("format,mime,extension", FORMATS)
def test_reference_payload_uses_verified_actual_mime(format, mime, extension):
    provider, model = PROVIDERS[0]
    http = Http(lambda *_: httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(encoded("PNG")).decode()}]}))
    content = encoded(format)
    asyncio.run(ImageApiClient(provider, http).generate(request(provider, model), "synthetic", content))
    url = http.calls[0][2]["json"]["input_references"][0]["image_url"]["url"]
    prefix, body = url.split(",", 1)
    assert prefix == f"data:{mime};base64" and base64.b64decode(body) == content


def test_png_only_transfer_conversion_validates_final_bytes_without_changing_asset():
    endpoint = deepcopy(CATALOG["nanogpt:krea-v2/turbo"]["payload"]["endpoints"][0])
    route = endpoint["input_reference_constraints"]["route"]
    route["formats"] = ["png"]
    original = encoded("JPEG")
    transferred, info = prepare_api_reference(endpoint, original)
    assert info.content_type == "image/png" and original == encoded("JPEG")
    route["max_bytes"] = len(transferred) - 1
    with pytest.raises(ImagePreparationError, match="reference_bytes_invalid"):
        prepare_api_reference(endpoint, original)
    route["max_bytes"] = 100000
    with pytest.raises(ImagePreparationError, match="reference_width_invalid"):
        prepare_api_reference(endpoint, encoded("PNG", size=(7, 18)))
    route["formats"] = ["jpeg"]
    with pytest.raises(ImagePreparationError, match="reference_format_invalid"):
        prepare_api_reference(endpoint, encoded("WEBP"))


@pytest.mark.parametrize("format,mime,extension", FORMATS)
def test_draft_expiry_orphans_references_integrity_and_backup_fixture(tmp_path, format, mime, extension):
    import shutil
    sessions, media, _ = configured(tmp_path)
    content = encoded(format)
    now = datetime.now(timezone.utc)
    with sessions() as db:
        ready = media.assets.upload(db, owner_id=OWNER, scope_kind="world", scope_id="social-uow-world", content_type=mime, content=content, draft=False)
        expired = media.assets.upload(db, owner_id=OWNER, scope_kind="world", scope_id="social-uow-world", content_type=mime, content=content)
        expired.expires_at = now - timedelta(seconds=1)
        db.commit()
        old = now.timestamp() - 90000
        orphan = media.assets.root / ("b" * 32 + "." + extension); orphan.write_bytes(content); os.utime(orphan, (old, old))
        arbitrary = media.assets.root / ("user-photo." + extension); arbitrary.write_bytes(content); os.utime(arbitrary, (old, old))
        fresh = media.assets.root / ("c" * 32 + "." + extension); fresh.write_bytes(content)
        os.utime(media.assets.path(ready), (old, old))
        # Restore a managed-image fixture through the same owned reader. This
        # verifies media storage metadata, not the full operational backup UI.
        restored_root = tmp_path / "restored-media"
        shutil.copytree(media.assets.root, restored_root)
        restored = AssetService(restored_root, media.assets.authorize_scope)
        assert restored.read(db, owner_id=OWNER, asset_id=ready.id)[1] == content
        media.assets.expire_drafts(db, now)
        assert not media.assets.path(expired).exists() and not orphan.exists()
        assert arbitrary.exists() and fresh.exists() and media.assets.path(ready).exists()
        media.assets.path(ready).write_bytes(content + b"changed")
        with pytest.raises(InvalidProfileMediaError, match="asset_content_changed"):
            media.assets.read(db, owner_id=OWNER, asset_id=ready.id)


@pytest.mark.parametrize("format,mime,extension", FORMATS)
def test_authenticated_http_content_matches_bytes_and_keeps_owner_scope(tmp_path, format, mime, extension):
    from types import SimpleNamespace
    from sqlalchemy.orm import sessionmaker
    from app.domains.media.router import router
    from app.runtime.media.composition import MediaRuntime
    from chat.test_p8_l_d_world_chat_api import _fixture, _seed, FRONTEND_HEADERS
    client, engine, principal = _fixture()
    owner, outsider, _ = _seed(engine, principal)
    runtime = MediaRuntime(sessionmaker(engine), SimpleNamespace(media_root_path=tmp_path))
    client.app.state.media_runtime = runtime
    client.app.include_router(router, prefix="/api/v1")
    content = encoded(format)
    try:
        asset = client.post("/api/v1/media/assets", headers=FRONTEND_HEADERS, json={"scope_kind": "world", "scope_id": "world-a",
            "content_type": mime, "data_base64": base64.b64encode(content).decode()}).json()
        response = client.get(asset["url"])
        assert response.status_code == 200 and response.content == content
        assert response.headers["content-type"] == mime
        assert response.headers["cache-control"] == "private, no-store" and response.headers["x-content-type-options"] == "nosniff"
        principal["user"] = outsider
        assert client.get(asset["url"]).status_code == 422
    finally:
        client.close(); engine.dispose()


@pytest.mark.parametrize("format,mime,extension", FORMATS)
def test_profile_and_override_reference_keep_format_and_priority(tmp_path, format, mime, extension):
    from app.domains.characters.models import Character, AgentImageGenerationSetting
    from image_integration.test_generation_lifecycle import CHARACTER
    sessions, media, _ = configured(tmp_path)
    media.settings.media_url_path = "/media"
    content = encoded(format)
    with sessions() as db:
        character = db.get(Character, CHARACTER)
        setting = db.get(AgentImageGenerationSetting, CHARACTER)
        profile = media.settings.media_root_path / ("profile." + extension)
        profile.parent.mkdir(parents=True, exist_ok=True)
        profile.write_bytes(content)
        character.avatar_url = "/media/" + profile.name
        ref = media._reference(db, OWNER, character, setting, True)
        asset, actual = media.assets.read(db, owner_id=OWNER, asset_id=ref.asset_id)
        assert ref.source == "profile" and actual == content and asset.content_type == mime
        setting.reference_asset_id = asset.id
        assert media._reference(db, OWNER, character, setting, True).source == "override"
        assert profile.read_bytes() == content
        assert media._reference(db, OWNER, character, setting, False).asset_id is None


@pytest.mark.parametrize("format,mime,extension", FORMATS)
def test_comfy_multipart_and_novel_send_only_png_keep_original(tmp_path, format, mime, extension):
    from app.integrations.comfy_images import ComfyImageClient
    from app.integrations.novelai_images import precise_pixels
    from app.domains.media.generation_contracts import ComfyOptions
    from image_integration.test_providers import samples, object_info
    sample = samples()["reference"]
    options = ComfyOptions(base_url="http://127.0.0.1:8188", workflow=sample["workflow"], text_workflow=samples()["text"]["workflow"], values=sample["values"])
    def respond(method, url, args):
        if url.endswith("/object_info"):
            return httpx.Response(200, json=object_info())
        if url.endswith("/upload/image"):
            return httpx.Response(200, json={"name": "uploaded.png", "subfolder": "", "type": "input"})
        if url.endswith("/prompt"):
            return httpx.Response(200, json={"prompt_id": "receipt-1", "node_errors": {}})
        if "/history/" in url:
            return httpx.Response(200, json={"receipt-1": {"outputs": {"7": {"images": [{"filename": "output.png", "subfolder": "", "type": "output"}]}}}})
        return httpx.Response(200, content=encoded("PNG"), headers={"content-type": "image/png"})
    http = Http(respond)
    content = encoded(format)
    async def received(_):
        pass
    asyncio.run(ComfyImageClient(options.base_url, http).generate(GenerationRequest("comfyui", "workflow", "scene", "blur", options.model_dump(), EffectiveReference(True)),
        None, content, on_receipt=received))
    upload = next(args["files"]["image"] for _, url, args in http.calls if url.endswith("/upload/image"))
    assert upload == ("angmoo-reference." + extension, content, mime)
    converted = base64.b64decode(precise_pixels(content), validate=True)
    assert inspect_image_bytes(converted, max_bytes=10 * 1024 * 1024).content_type == "image/png"
    assert content == encoded(format)


def test_cleanup_does_not_follow_opaque_symlink(tmp_path):
    sessions, media, _ = configured(tmp_path)
    target = tmp_path / "keep.jpg"; target.write_bytes(encoded("JPEG"))
    link = media.assets.root / ("d" * 32 + ".jpg")
    media.assets.root.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("host does not permit symlink creation")
    with sessions() as db:
        media.assets.expire_drafts(db, datetime.now(timezone.utc) + timedelta(days=3))
    assert link.is_symlink() and target.exists()
