"""Exercise the production NovelAI path with synthetic HTTP, never real keys."""
import asyncio
import base64
from io import BytesIO
import json
from zipfile import ZipFile

import httpx
import pytest
from sqlalchemy import func, select

from app.domains.identity.models import User
from app.domains.media.generation_contracts import EffectiveReference, GenerationRequest, ImagePreparationError, NovelOptions
from app.domains.media.setting_schemas import GenerationSettingsWrite
from app.domains.social.models.image_intents import ImageGenerationAttempt, ImageIntent
from app.domains.social.models.posts import Post, PostImageGenerationJob, PostMedia
from app.integrations.image_api import ImageHttp
from app.integrations.novelai_images import MODEL, NovelImageClient, validate_t5_prompt
from image_integration.test_generation_lifecycle import CHARACTER, OWNER, POST, admit, configured
from image_integration.test_providers import Http, png


@pytest.mark.parametrize("mode,zip_result", [("opus_free", False), ("allow_anlas", True)])
def test_production_novelai_connects_enables_and_attaches_without_exactness_override(tmp_path, mode, zip_result):
    sessions, media, _ = configured(tmp_path, "novelai", MODEL)
    calls = []
    def respond(request):
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"tier": 3, "active": True, "expiresAt": 9999999999})
        if zip_result:
            result = BytesIO()
            with ZipFile(result, "w") as archive:
                archive.writestr("image_0.png", png())
            return httpx.Response(200, content=result.getvalue(), headers={"content-type": "application/zip"})
        return httpx.Response(200, json={"images": [{"image": base64.b64encode(png()).decode()}]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond), trust_env=False) as transport:
            media.clients["novelai"] = NovelImageClient(ImageHttp(transport))
            with sessions() as db:
                owner = db.get(User, OWNER)
                saved = media.read_generation(db, owner, CHARACTER)
                data = GenerationSettingsWrite(expected_revision=saved["revision"], provider="novelai", model=MODEL,
                    options=NovelOptions(mode=mode).model_dump(), appearance="short hair", style="ink", negative="blur",
                    auto_enabled=True, daily_limit=4)
                connection = await media.validate_connection(db, owner, CHARACTER, data)
                assert connection["ready"] and connection["opus_verified"]
                assert connection["prompt_validation"]["exact_verified"] is False
                saved = media.write_generation(db, owner, CHARACTER, data, validated_connection=connection)
                assert saved["auto_enabled"] and saved["effective_auto_enabled"]
                assert saved["prompt_validation"]["generation_available"]
                db.commit()
            identity = admit(sessions, media)
            await media.worker.process(identity)
            await media.worker.process(identity)
            with sessions() as db:
                assert db.get(PostImageGenerationJob, identity).status == "succeeded"
                assert db.scalar(select(func.count()).select_from(PostMedia)) == 1
                assert db.scalar(select(ImageIntent)).state == "attached"
                assert db.scalar(select(func.count()).select_from(ImageGenerationAttempt)) == 1
                assert db.get(Post, POST).body
            assert media.clients["novelai"].prompt_validation()["exact_verified"] is False
    asyncio.run(run())
    submissions = [request for request in calls if request.method == "POST"]
    assert len(submissions) == 1
    body = json.loads(submissions[0].content)
    assert body["input"] == "ink, short hair, reading at a desk"
    assert body["parameters"]["negative_prompt"] == "blur"
    assert body["parameters"]["n_samples"] == 1
    assert not any("reference" in name for name in body["parameters"])


def test_weighted_prompt_is_sent_without_rewriting_or_claiming_exact_count():
    positive = "1girl, {{{blue hair}}}, 1.5::reading at a desk ::"
    negative = "0.5::blur ::, [low quality]"
    http = Http(lambda *_: httpx.Response(200, json={"images": [{"image": base64.b64encode(png()).decode()}]}))
    client = NovelImageClient(http)
    request = GenerationRequest("novelai", MODEL, positive, negative, NovelOptions(mode="allow_anlas").model_dump(), EffectiveReference(False))
    assert asyncio.run(client.generate(request, "synthetic-only", None)).content == png()
    body = http.calls[0][2]["json"]
    assert body["input"] == positive
    assert body["parameters"]["v4_prompt"]["caption"]["base_caption"] == positive
    assert body["parameters"]["v4_negative_prompt"]["caption"]["base_caption"] == negative
    assert client.prompt_validation()["state"] == "local_preflight"
    assert client.prompt_validation()["exact_verified"] is False


@pytest.mark.parametrize("count,accepted", [(510, True), (511, True), (512, False)])
def test_pinned_local_token_budget_boundary_includes_eos(count, accepted):
    if accepted:
        assert validate_t5_prompt("hello " * count) == count + 1
    else:
        with pytest.raises(ImagePreparationError, match="novelai_t5_prompt_limit"):
            validate_t5_prompt("hello " * count)


@pytest.mark.parametrize("scene,reason", [("한국어 장면", "novelai_prompt_contains_unsupported_text"), ("a " * 600, "novelai_t5_prompt_limit")])
def test_invalid_scene_is_blocked_before_reservation_or_http(tmp_path, scene, reason):
    sessions, media, _ = configured(tmp_path, "novelai", MODEL)
    http = Http(lambda *_: pytest.fail("invalid input must not reach the service"))
    media.clients["novelai"] = NovelImageClient(http)
    assert admit(sessions, media, scene) is None
    with sessions() as db:
        assert db.scalar(select(ImageIntent)).reason == reason
        assert db.scalar(select(func.count()).select_from(ImageGenerationAttempt)) == 0
        assert db.get(Post, POST).body
    assert http.calls == []


@pytest.mark.parametrize("field", ["style", "negative"])
def test_enabling_validates_fixed_prompt_inputs_before_settings_save(tmp_path, field):
    sessions, media, _ = configured(tmp_path, "novelai", MODEL)
    with sessions() as db:
        owner = db.get(User, OWNER)
        saved = media.read_generation(db, owner, CHARACTER)
        data = GenerationSettingsWrite(expected_revision=saved["revision"], provider="novelai", model=MODEL,
            auto_enabled=True, daily_limit=4, options=NovelOptions(mode="allow_anlas").model_dump(), **{field: "한글"})
        with pytest.raises(ImagePreparationError, match="unsupported_text"):
            media.write_generation(db, owner, CHARACTER, data)
        assert media.read_generation(db, owner, CHARACTER)["revision"] == saved["revision"]


@pytest.mark.parametrize("code,status", [(400, "failed"), (500, "outcome_unknown")])
def test_provider_rejection_and_unknown_outcome_preserve_post_and_do_not_auto_resubmit(tmp_path, code, status):
    sessions, media, _ = configured(tmp_path, "novelai", MODEL)
    calls = []
    def reject(request):
        calls.append(request)
        return httpx.Response(code, json={"error": "synthetic-only private provider detail"})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(reject), trust_env=False) as transport:
            media.clients["novelai"] = NovelImageClient(ImageHttp(transport))
            identity = admit(sessions, media)
            await media.worker.process(identity)
            await media.worker.process(identity)
            with sessions() as db:
                job = db.get(PostImageGenerationJob, identity)
                assert job.status == status and job.failure_class == f"provider_http_{code}"
                assert db.get(Post, POST).body
                assert db.scalar(select(func.count()).select_from(PostMedia)) == 0
                if status == "outcome_unknown":
                    with pytest.raises(ImagePreparationError, match="image_outcome_unknown_no_resubmit"):
                        media.worker.retry(db, OWNER, POST, media.quota_day())
    asyncio.run(run())
    assert len(calls) == 1 and calls[0].method == "POST"


@pytest.mark.parametrize("field", ["appearance", "negative"])
def test_connection_check_does_not_mark_invalid_fixed_inputs_ready(tmp_path, field):
    sessions, media, _ = configured(tmp_path, "novelai", MODEL)
    http = Http(lambda *_: pytest.fail("input preparation must precede the account request"))
    media.clients["novelai"] = NovelImageClient(http)
    with sessions() as db:
        owner = db.get(User, OWNER)
        data = GenerationSettingsWrite(expected_revision=1, provider="novelai", model=MODEL,
            options=NovelOptions().model_dump(), **{field: "한글"})
        with pytest.raises(ImagePreparationError, match="unsupported_text"):
            asyncio.run(media.validate_connection(db, owner, CHARACTER, data))
    assert http.calls == []


def test_weight_controls_do_not_consume_text_budget_or_hide_unsupported_content():
    assert validate_t5_prompt("{{{hello}}}") == 2
    assert validate_t5_prompt("-1.5::hello ::") == 2
    assert validate_t5_prompt("[[hello]]" * 511) == 512
    with pytest.raises(ImagePreparationError, match="prompt_limit"):
        validate_t5_prompt("[[hello]]" * 512)
    with pytest.raises(ImagePreparationError, match="unsupported_text"):
        validate_t5_prompt("{{한국어}}")
    with pytest.raises(ImagePreparationError, match="prompt_empty"):
        validate_t5_prompt("{{}} ::")
