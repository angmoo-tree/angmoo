"""Failure boundaries, reservations and product recovery without paid services."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib

import pytest
from sqlalchemy import func, select

from app.domains.chat.models import MessageMessage, MessageAttachment
from app.domains.chat.schemas import WorldChatMessageCreate, WorldChatRetryCreate
from app.domains.chat.exceptions import MessageValidationError
from app.domains.characters.models import AgentImageGenerationSetting, AgentCreationDraft, Character, CharacterCardSource
from app.domains.media.generation_contracts import ImagePreparationError, GenerationRequest, EffectiveReference, NovelOptions
from app.domains.media.setting_schemas import GenerationSettingsWrite
from app.domains.media.models import MediaAsset, InterpretationAttempt, ImageInterpretation, InterpretationSetting
from app.domains.media.api_image_policy import validate_api_options, validate_reference_metadata
from app.domains.social.models.posts import PostImageGenerationJob, PostMedia
from app.domains.social.models.image_intents import ImageGenerationAttempt, ImageIntent
from app.integrations.novelai_images import NovelImageClient
from app.domains.social.service.image_intent_generation import GenerationWorker
from image_integration.test_generation_lifecycle import configured, admit, OWNER, CHARACTER, POST
from image_integration.test_providers import Http, CATALOG, png
from image_integration.test_interpretation import FakeInterpreter, image_db, prepared
from image_integration.chat_support import synthetic_chat
from image_integration.test_chat_attachments import upload, stream


@pytest.mark.parametrize("suffix", ["json.tmp", "pixels.tmp"])
def test_received_journal_recovers_disk_error_without_resubmit(tmp_path, monkeypatch, suffix):
    sessions, media, provider = configured(tmp_path)
    identity = admit(sessions, media)
    original = __import__("pathlib").Path.open
    def fail_once(path, *args, **kwargs):
        if path.name == f"{identity}.{suffix}":
            raise OSError("synthetic disk error")
        return original(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(__import__("pathlib").Path, "open", fail_once)
        asyncio.run(media.worker.process(identity))
    with sessions() as db:
        assert db.get(PostImageGenerationJob, identity).status == "result_pending"
        assert db.scalar(select(ImageGenerationAttempt)).status == "result_received"
    if suffix == "pixels.tmp":
        # A new worker has no memory buffer. Its complete atomic journal suffices.
        media.worker = GenerationWorker(sessions, media.assets, media, spool=media.worker.spool)
    asyncio.run(media.worker.process(identity))
    with sessions() as db:
        assert db.get(PostImageGenerationJob, identity).status == "succeeded"
        assert db.scalar(select(PostMedia)) is not None
    assert provider.calls == 1


def test_received_result_lost_with_process_never_allows_new_submission(tmp_path, monkeypatch):
    sessions, media, provider = configured(tmp_path)
    identity = admit(sessions, media)
    def fail_write(*args):
        raise OSError("synthetic unavailable disk")
    monkeypatch.setattr(media.worker, "_write_received", fail_write)
    asyncio.run(media.worker.process(identity))
    media.worker = GenerationWorker(sessions, media.assets, media, spool=media.worker.spool)
    asyncio.run(media.worker.process(identity))
    with sessions() as db:
        row = db.get(PostImageGenerationJob, identity)
        assert row.status == "outcome_unknown" and not media.worker.view(row)["retryable"]
        with pytest.raises(ImagePreparationError, match="no_resubmit"):
            media.worker.retry(db, OWNER, POST, media.quota_day())
    assert provider.calls == 1


@pytest.mark.parametrize("scene,error", [(None, None), ([], None), ("x" * 1801, None), ("", "image_prompt_invalid_type")])
def test_invalid_scene_is_distinct_from_normal_empty_scene(tmp_path, scene, error):
    from types import SimpleNamespace
    from app.domains.social.models.posts import Post
    sessions, media, provider = configured(tmp_path)
    with sessions() as db:
        intent = media.admit_post(db, post=db.get(Post, POST), owner_id=OWNER, character_id=CHARACTER,
            draft=SimpleNamespace(_image_prompt=scene, _image_error=error))
        assert intent.state == "blocked" and intent.reason
        assert db.scalar(select(PostImageGenerationJob)) is None
        assert db.get(Post, POST).body
    assert provider.calls == 0


def test_admission_is_shared_reserved_and_rolled_back_without_ai(image_db, tmp_path):
    fake = FakeInterpreter()
    _, service, (identity,) = prepared(image_db, tmp_path, fake, cap=1)
    with image_db() as db:
        admitted = service.admit(db, "owner", identity)
        assert admitted.status == "queued"
        assert service.admit(db, "owner", identity).id == admitted.id
        assert db.scalar(select(func.count()).select_from(InterpretationAttempt)) == 1
        assert fake.calls == 0
        db.rollback()
    with image_db() as db:
        assert db.scalar(select(func.count()).select_from(InterpretationAttempt)) == 0
        assert db.scalar(select(func.count()).select_from(ImageInterpretation)) == 0


def test_competing_chat_and_sns_scopes_atomically_reserve_last_analysis(image_db, tmp_path):
    fake = FakeInterpreter()
    assets, service, identities = prepared(image_db, tmp_path, fake, cap=1, scopes=("chat", "sns"))
    with image_db() as db:
        db.get(MediaAsset, identities[1]).scope_kind = "world"
        db.commit()
    def reserve(identity):
        with image_db() as db:
            try:
                service.admit(db, "owner", identity)
                db.commit()
                return "reserved"
            except ImagePreparationError as error:
                db.rollback()
                assert str(error) == "interpretation_daily_limit_reached"
                return "blocked"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, identities)) == ["blocked", "reserved"]
    with image_db() as db:
        assert db.scalar(select(func.count()).select_from(InterpretationAttempt)) == 1
    assert fake.calls == 0


def test_reserved_job_is_consumed_once_and_cache_reuses_off(image_db, tmp_path):
    fake = FakeInterpreter()
    _, service, (identity,) = prepared(image_db, tmp_path, fake, cap=1)
    with image_db() as db:
        shared_id = service.admit(db, "owner", identity).id
        db.commit()
    async def consume():
        with image_db() as first, image_db() as second:
            results = await asyncio.gather(service.interpret(first, "owner", identity), service.interpret(second, "owner", identity))
            assert [row.id for row in results] == [shared_id, shared_id]
    asyncio.run(consume())
    with image_db() as db:
        assert db.scalar(select(func.count()).select_from(InterpretationAttempt)) == 1
        db.get(InterpretationSetting, "owner").enabled = False
        db.commit()
        assert service.admit(db, "owner", identity).id == shared_id
    assert fake.calls == 1


def test_chat_does_not_replace_reserved_analysis_after_settings_change(tmp_path):
    fake = FakeInterpreter()
    chat = synthetic_chat(tmp_path, fake)
    try:
        asset = upload(chat)
        accepted = chat.generation.accept_world_message(chat.db, chat.owner, chat.world_id, chat.thread_id,
            WorldChatMessageCreate(content="예약한 사진", attachment_asset_id=asset, idempotency_key="image-admission-change-001"))
        reservation = chat.db.get(MessageAttachment, accepted.user_message.id).interpretation_id
        setting = chat.db.get(InterpretationSetting, chat.owner.id)
        setting.thinking_level = "high"
        setting.revision += 1
        chat.db.commit()
        events = asyncio.run(stream(chat, accepted.response_request.request_id))
        assert events[-1].event_type.value == "failed"
        assert chat.db.get(MessageAttachment, accepted.user_message.id).interpretation_id == reservation
        assert chat.db.scalar(select(func.count()).select_from(InterpretationAttempt)) == 1
        assert fake.calls == 0
    finally:
        chat.source.close()


def test_chat_retry_binding_uses_new_cache_without_reusing_old_snapshot(tmp_path):
    fake = FakeInterpreter()
    chat = synthetic_chat(tmp_path, fake)
    try:
        asset = upload(chat)
        accepted = chat.generation.accept_world_message(chat.db, chat.owner, chat.world_id, chat.thread_id,
            WorldChatMessageCreate(content="같은 사진", attachment_asset_id=asset, idempotency_key="image-cache-renewal-001"))
        asyncio.run(stream(chat, accepted.response_request.request_id))
        attachment = chat.db.get(MessageAttachment, accepted.user_message.id)
        old_id = attachment.interpretation_id
        assert attachment.snapshot_json and fake.calls == 1
        chat.db.get(InterpretationSetting, chat.owner.id).thinking_level = "high"
        chat.db.commit()
        chat.generation.images.reserve_retry(chat.db, chat.owner.id, chat.thread_id, accepted.user_message.id)
        assert attachment.interpretation_id != old_id and attachment.snapshot_json is None
        assert chat.db.get(ImageInterpretation, old_id).status == "succeeded"
        chat.db.commit()
        value = asyncio.run(chat.generation.images.observation(chat.db, chat.owner.id, chat.thread_id, accepted.user_message.id))
        assert value["interpretation_id"] == attachment.interpretation_id and value["asset_id"] == asset
        assert fake.calls == 2
    finally:
        chat.source.close()


@pytest.mark.parametrize("field,value", [("width", 7), ("height", 7), ("width", 16385), ("byte_size", 31457281), ("content_type", "image/gif")])
def test_reference_endpoint_pixel_mime_and_byte_boundaries(field, value):
    endpoint = CATALOG["nanogpt:krea-v2/turbo"]["payload"]["endpoints"][0]
    valid = {"width": 8, "height": 8, "byte_size": 31457280, "content_type": "image/png"}
    validate_reference_metadata(endpoint, **valid)
    with pytest.raises(ImagePreparationError):
        validate_reference_metadata(endpoint, **{**valid, field: value})


def test_model_specific_option_case_and_profiles_are_not_interchangeable():
    nano = CATALOG["nanogpt:krea-v2/turbo"]["payload"]["endpoints"][0]
    router = CATALOG["openrouter:krea/krea-2-medium-turbo"]["payload"]["endpoints"][0]
    assert validate_api_options("nanogpt", nano, {"resolution": "1k"}) == {"resolution": "1k"}
    assert validate_api_options("openrouter", router, {"resolution": "1K"}) == {"resolution": "1K"}
    with pytest.raises(ImagePreparationError):
        validate_api_options("openrouter", router, {"resolution": "1k"})


def test_novel_exact_validation_is_unverified_and_blocks_before_any_http():
    http = Http(lambda *_: pytest.fail("unverified validation must precede any I/O"))
    client = NovelImageClient(http)
    assert client.prompt_validation()["resource_verified"]
    assert not client.prompt_validation()["exact_verified"]
    request = GenerationRequest("novelai", "nai-diffusion-4-5-full", "blue sky", "blur", NovelOptions().model_dump(), EffectiveReference(False))
    with pytest.raises(ImagePreparationError, match="prompt_validation_unverified"):
        asyncio.run(client.generate(request, "synthetic", None))
    assert http.calls == []


def test_novel_settings_and_existing_queued_job_do_not_bypass_unverified_gate(tmp_path):
    sessions, media, provider = configured(tmp_path, "novelai", "nai-diffusion-4-5-full")
    job_id = admit(sessions, media)
    media.clients["novelai"] = NovelImageClient(Http(lambda *_: pytest.fail("no API")))
    with sessions() as db:
        from app.domains.identity.models import User
        user = db.get(User, OWNER)
        current = media.read_generation(db, user, CHARACTER)
        assert current["prompt_validation"]["exact_verified"] is False
        assert current["effective_auto_enabled"] is False and current["auto_enabled"] is True
        with pytest.raises(ImagePreparationError, match="prompt_validation_unverified"):
            media.write_generation(db, user, CHARACTER, GenerationSettingsWrite(expected_revision=current["revision"],
                provider="novelai", model="nai-diffusion-4-5-full", auto_enabled=True, daily_limit=4))
    asyncio.run(media.worker.process(job_id))
    with sessions() as db:
        assert db.get(PostImageGenerationJob, job_id).failure_class == "novelai_prompt_validation_unverified"
        assert db.scalar(select(ImageGenerationAttempt)).status == "released"
    assert provider.calls == 0


def test_reference_settings_resolve_actual_source_without_creating_assets(tmp_path):
    from app.domains.identity.models import User
    sessions, media, provider = configured(tmp_path)
    media.settings.media_url_path = "/media"
    with sessions() as db:
        user, character = db.get(User, OWNER), db.get(Character, CHARACTER)
        initial = media.read_generation(db, user, CHARACTER)
        assert initial["reference_state"]["preferred"] and initial["reference_state"]["status"] == "missing"
        character.avatar_url = "/media/characters/profile.png"
        path = media.settings.media_root_path / "characters/profile.png"
        path.parent.mkdir(parents=True)
        path.write_bytes(png())
        assert media.read_generation(db, user, CHARACTER)["reference_state"]["source"] == "profile"
        db.add(AgentCreationDraft(id="review-card-draft", user_id=OWNER, model="synthetic", expires_at=datetime.now(timezone.utc)+timedelta(days=1)))
        db.flush()
        db.add(CharacterCardSource(id="review-card", owner_id=OWNER, draft_id="review-card-draft", character_id=CHARACTER,
            source_bytes=png(), source_sha256=hashlib.sha256(png()).hexdigest(), source_format="png", parser_version="synthetic", card_version=2))
        db.flush()
        count = db.scalar(select(func.count()).select_from(MediaAsset))
        state = media.read_generation(db, user, CHARACTER)["reference_state"]
        assert state["source"] == "card" and state["applied"]
        assert db.scalar(select(func.count()).select_from(MediaAsset)) == count
        assert db.get(AgentImageGenerationSetting, CHARACTER).card_asset_id is None
        explicit = media.assets.upload(db, owner_id=OWNER, scope_kind="character", scope_id=CHARACTER,
            content_type="image/png", content=png(), draft=False)
        db.get(AgentImageGenerationSetting, CHARACTER).reference_asset_id = explicit.id
        assert media.read_generation(db, user, CHARACTER)["reference_state"]["source"] == "override"
        media.assets.path(explicit).write_bytes(b"invalid synthetic pixels")
        invalid = media.read_generation(db, user, CHARACTER)["reference_state"]
        assert invalid["status"] == "invalid" and invalid["generation_path"] == "unavailable"
        assert not invalid["applied"] and not invalid["scene_only"]
    assert provider.calls == 0


@pytest.mark.parametrize("body", ["", "사진 없이도 이 질문에 답해 줘."])
def test_chat_analysis_failure_exposes_explicit_text_recovery_without_mutating_original(tmp_path, body):
    class Failed(FakeInterpreter):
        async def analyze(self, **kwargs):
            self.calls += 1
            raise ValueError("synthetic invalid analysis")
    fake = Failed()
    chat = synthetic_chat(tmp_path, fake, expect_image=False)
    try:
        asset = upload(chat)
        accepted = chat.generation.accept_world_message(chat.db, chat.owner, chat.world_id, chat.thread_id,
            WorldChatMessageCreate(content=body, attachment_asset_id=asset, idempotency_key="image-recovery-original-001"))
        assert accepted.response_request.image_analysis_state == "waiting"
        assert accepted.user_message.attachment.analysis_state == "pending"
        asyncio.run(stream(chat, accepted.response_request.request_id))
        failed = chat.generation.get_world_response_request(chat.db, chat.owner, chat.world_id, chat.thread_id, accepted.response_request.request_id)
        assert failed.image_analysis_state == "failed" and failed.can_retry_without_image == bool(body)
        request = WorldChatRetryCreate(failed_request_id=failed.request_id, idempotency_key="image-recovery-text-only-001", exclude_attachment=True)
        if not body:
            with pytest.raises(MessageValidationError, match="text_only_recovery_unavailable"):
                chat.generation.retry_world_response(chat.db, chat.owner, chat.world_id, chat.thread_id, request)
            return
        retried = chat.generation.retry_world_response(chat.db, chat.owner, chat.world_id, chat.thread_id, request)
        assert retried.response_request.image_analysis_state == "excluded"
        assert retried.response_request.response_slot_id == failed.response_slot_id
        assert retried.user_message.id == failed.user_message.id
        assert chat.generation.retry_world_response(chat.db, chat.owner, chat.world_id, chat.thread_id, request).outcome == "replayed"
        with pytest.raises(MessageValidationError, match="idempotency_conflict"):
            chat.generation.retry_world_response(chat.db, chat.owner, chat.world_id, chat.thread_id,
                request.model_copy(update={"exclude_attachment": False}))
        events = asyncio.run(stream(chat, retried.response_request.request_id))
        assert events[-1].event_type.value == "completed"
        assert chat.generation.get_world_response_request(chat.db, chat.owner, chat.world_id, chat.thread_id,
            retried.response_request.request_id).image_analysis_state == "excluded"
        assert chat.commands[-1].preflight.user_message == body and chat.commands[-1].image_evidence is None
        assert chat.db.get(MessageMessage, failed.user_message.id).content == body
        assert chat.db.get(MessageAttachment, failed.user_message.id).asset_id == asset
        assert chat.db.scalar(select(func.count()).select_from(InterpretationAttempt)) == 1
        assert fake.calls == 1
    finally:
        chat.source.close()
