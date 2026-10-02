"""Plan regressions: synthetic DB/files and no real network or credentials."""
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select, func

from tests.conftest import deny_external_network
from image_integration.test_generation_lifecycle import configured, admit, OWNER, CHARACTER, POST
from image_integration.test_providers import samples, object_info, Http, png
from image_integration.chat_support import synthetic_chat
from image_integration.test_interpretation import FakeInterpreter
from image_integration.test_chat_attachments import upload
from app.domains.social.models.posts import PostImageGenerationJob
from app.domains.social.models.image_intents import ImageGenerationAttempt, ImageIntent
from app.domains.media.generation_contracts import ImageSubmissionError
from app.domains.media.setting_schemas import GenerationSettingsWrite
from app.domains.identity.models import User
from app.domains.media.models import InterpretationSetting, InterpretationAttempt
from app.domains.chat.schemas import WorldChatMessageCreate
from app.integrations.comfy_images import ComfyImageClient
from app.integrations.image_api import ImageApiClient
from app.domains.media.generation_contracts import GenerationRequest, EffectiveReference, ImagePreparationError
from image_integration.test_providers import CATALOG
from io import BytesIO
from PIL import Image
import base64
import httpx


@pytest.fixture(autouse=True)
def isolated_review(deny_external_network):
    yield


def test_successful_generation_with_local_manifest_error_cannot_resubmit(tmp_path, monkeypatch):
    sessions, media, provider = configured(tmp_path)
    job_id = admit(sessions, media)
    original = Path.open

    def fail_manifest(path, *args, **kwargs):
        if path.name == f"{job_id}.json.tmp":
            raise OSError("synthetic manifest write failure")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as injected:
        injected.setattr(Path, "open", fail_manifest)
        asyncio.run(media.worker.process(job_id))
    with sessions() as db:
        job = db.get(PostImageGenerationJob, job_id)
        observed = {"status": job.status, "reason": job.failure_class, "calls": provider.calls}
        if media.worker.view(job)["retryable"]:
            media.worker.retry(db, OWNER, POST, media.quota_day())
            db.commit()
    asyncio.run(media.worker.process(job_id))
    assert provider.calls == 1, {**observed, "calls_after_retry": provider.calls}


def test_known_failed_comfy_job_retry_can_submit_a_new_attempt(tmp_path):
    sessions, media, provider = configured(tmp_path, "comfyui", "workflow")
    job_id = admit(sessions, media)
    original = provider.generate

    async def execution_failed(request, key, reference, *, on_submit, on_receipt, receipt=None):
        await on_submit()
        provider.calls += 1
        await on_receipt("failed-comfy-receipt")
        raise ImageSubmissionError("comfy_execution_failed")

    provider.generate = execution_failed
    asyncio.run(media.worker.process(job_id))
    provider.generate = original
    with sessions() as db:
        first = db.get(PostImageGenerationJob, job_id)
        assert first.status == "failed" and first.provider_receipt == "failed-comfy-receipt"
        media.worker.retry(db, OWNER, POST, media.quota_day())
        db.commit()
    asyncio.run(media.worker.process(job_id))
    with sessions() as db:
        final = db.get(PostImageGenerationJob, job_id)
        assert final.status == "succeeded", {"status": final.status, "reason": final.failure_class, "calls": provider.calls}


def test_text_workflow_applies_its_supported_negative_prompt(tmp_path):
    sessions, media, _ = configured(tmp_path, "comfyui", "workflow")
    reference = samples()["reference"]
    text = samples()["text"]
    del reference["workflow"]["bindings"]["negative"]
    with sessions() as db:
        user = db.get(User, OWNER)
        current = media.read_generation(db, user, CHARACTER)
        media.write_generation(db, user, CHARACTER, GenerationSettingsWrite(
            expected_revision=current["revision"], provider="comfyui", model="workflow",
            auto_enabled=True, daily_limit=4, appearance="short hair", style="ink", negative="blur",
            reference_enabled=True, options={"base_url":"http://127.0.0.1:8188",
                "workflow":reference["workflow"], "text_workflow":text["workflow"], "values":{}}),
            validated_connection={"ready":True,"reference_supported":True})
        db.commit()
        request, *_ = media.prepare_intent(db, OWNER, CHARACTER, "reading at a desk", None)
    calls = []

    def respond(method, url, kwargs):
        if url.endswith("/object_info"):
            return httpx.Response(200, json=object_info())
        if url.endswith("/prompt"):
            calls.append(kwargs["json"]["prompt"])
            return httpx.Response(200, json={"prompt_id":"text-receipt"})
        if "/history/" in url:
            return httpx.Response(200, json={"text-receipt":{"outputs":{"7":{"images":[{"filename":"result.png","type":"output"}]}}}})
        return httpx.Response(200, content=png(), headers={"content-type":"image/png"})

    async def received(value):
        pass

    asyncio.run(ComfyImageClient("http://127.0.0.1:8188", Http(respond)).generate(request, None, None, on_receipt=received))
    binding = text["workflow"]["bindings"]["negative"]
    assert calls[0][binding["node_id"]]["inputs"][binding["input_name"]] == "blur", {"prepared_negative":request.negative}


def test_chat_acceptance_reserves_analysis_budget_before_returning(tmp_path):
    chat = synthetic_chat(tmp_path, FakeInterpreter())
    try:
        asset_id = upload(chat)
        chat.db.get(InterpretationSetting, chat.owner.id).daily_limit = 1
        chat.db.commit()
        chat.generation.accept_world_message(chat.db, chat.owner, chat.world_id, chat.thread_id,
            WorldChatMessageCreate(content="", attachment_asset_id=asset_id, idempotency_key="review-admission-0001"))
        attempts = chat.db.scalar(select(func.count()).select_from(InterpretationAttempt))
        assert attempts == 1, {"reserved_attempts_at_acceptance":attempts}
    finally:
        chat.source.close()


def test_nanogpt_reference_obeys_recorded_endpoint_pixel_constraints():
    endpoint = CATALOG["nanogpt:krea-v2/turbo"]["payload"]["endpoints"][0]
    assert endpoint["input_reference_constraints"]["route"]["min_width"] == 8
    buffer = BytesIO()
    Image.new("RGB", (1, 1), "blue").save(buffer, "PNG")
    http = Http(lambda *_: httpx.Response(200, json={"data":[{"b64_json":base64.b64encode(png()).decode(),"media_type":"image/png"}]}))
    request = GenerationRequest("nanogpt", "krea-v2/turbo", "scene", None, {}, EffectiveReference(True), endpoint)
    with pytest.raises(ImagePreparationError):
        asyncio.run(ImageApiClient("nanogpt", http).generate(request, "synthetic", buffer.getvalue()))
    assert not http.calls


def test_saved_ready_nanogpt_profile_rejects_unsupported_resolution(tmp_path):
    sessions, media, _ = configured(tmp_path)
    with sessions() as db:
        owner = db.get(User, OWNER)
        saved = media.read_generation(db, owner, CHARACTER)
        with pytest.raises(ImagePreparationError):
            media.write_generation(db, owner, CHARACTER, GenerationSettingsWrite(
                expected_revision=saved["revision"], provider="nanogpt", model="krea-v2/turbo",
                auto_enabled=True, daily_limit=4, options={"resolution":"not-a-supported-resolution"}))


def test_valid_empty_routine_scene_means_no_image_intent(tmp_path):
    sessions, media, provider = configured(tmp_path)
    assert admit(sessions, media, "") is None
    with sessions() as db:
        intent = db.scalar(select(ImageIntent))
        assert intent is None, {"state":intent.state,"reason":intent.reason}
    assert provider.calls == 0
