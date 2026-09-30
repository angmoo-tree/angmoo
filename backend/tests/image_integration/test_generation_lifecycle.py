import asyncio
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select, func

from social.test_l4_social_write_uow import _session_factory
from image_integration.test_providers import png, CATALOG, samples
from app.domains.identity.models import User
from app.domains.characters.models import AgentImageGenerationSetting, Character
from app.domains.characters.service.generation_settings import write_settings, read_settings
from app.domains.media.setting_schemas import GenerationSettingsWrite
from app.domains.media.generation_contracts import NovelOptions, ImageResult, ImagePreparationError, ImageSubmissionError
from app.domains.social.models.posts import Post, PostMedia, PostImageGenerationJob
from app.domains.social.models.image_intents import ImageIntent, ImageGenerationAttempt
from app.runtime.media.composition import MediaRuntime

OWNER = "social-uow-owner"
CHARACTER = "social-uow-autonomous-character"
POST = "social-uow-target-post"


class Provider:
    def __init__(self, provider, model):
        self.provider, self.model, self.calls = provider, model, 0
        self.after_submit = None
        self.error = None
    async def discover(self, model):
        return CATALOG[f"{self.provider}:{model}"]["payload"]["endpoints"][0]
    async def generate(self, request, key, reference, *, on_submit=None, on_receipt=None, receipt=None):
        if self.error == "preparation":
            raise ImagePreparationError("test_preparation_failure")
        if receipt is None:
            await on_submit()
            self.calls += 1
        if self.after_submit:
            self.after_submit()
        await asyncio.sleep(.01)
        if self.error == "unknown":
            raise ImageSubmissionError("test_timeout", outcome_unknown=True)
        if on_receipt:
            await on_receipt("comfy-receipt")
        assert request.positive == "ink, short hair, reading at a desk"
        assert request.negative == ("blur" if self.provider in {"novelai", "comfyui"} else None)
        return ImageResult(png(), "image/png", receipt="comfy-receipt" if on_receipt else None)


def configured(tmp_path, provider="nanogpt", model="krea-v2/turbo", cap=4):
    sessions = _session_factory(tmp_path)
    fake = Provider(provider, model)
    media = MediaRuntime(sessions, SimpleNamespace(media_root_path=tmp_path / "media"), clients={provider: fake})
    options = NovelOptions(mode="allow_anlas").model_dump() if provider == "novelai" else {"base_url": "http://127.0.0.1:8188", "workflow": samples()["text"]["workflow"], "values": samples()["text"]["values"]} if provider == "comfyui" else {}
    connection = {"ready": True, "reference_supported": provider != "comfyui"}
    if provider in {"nanogpt", "openrouter"}:
        connection["endpoint"] = CATALOG[f"{provider}:{model}"]["payload"]["endpoints"][0]
    with sessions() as db:
        owner = db.get(User, OWNER)
        setting = media.read_generation(db, owner, CHARACTER)
        media.write_generation(db, owner, CHARACTER, GenerationSettingsWrite(expected_revision=setting["revision"],
            provider=provider, model=model, auto_enabled=True, daily_limit=cap, installation_daily_limit=cap,
            appearance="short hair", style="ink", negative="blur", options=options, api_key="only-a-fake-key"),
            validated_connection=connection)
        db.commit()
    return sessions, media, fake


def admit(sessions, media, scene="reading at a desk"):
    with sessions() as db:
        intent = media.admit_post(db, post=db.get(Post, POST), owner_id=OWNER, character_id=CHARACTER,
            draft=SimpleNamespace(_image_prompt=scene, _image_error=None))
        db.commit()
        job = db.scalar(select(PostImageGenerationJob).where(PostImageGenerationJob.intent_id == intent.id))
        return job.id if job else None


@pytest.mark.parametrize("provider,model", [("novelai", "nai-diffusion-4-5-full"), ("comfyui", "workflow"), ("nanogpt", "krea-v2/turbo"), ("openrouter", "google/gemini-3.1-flash-image")])
def test_four_providers_admit_once_and_concurrent_workers_submit_once(tmp_path, provider, model):
    sessions, media, fake = configured(tmp_path, provider, model)
    identity = admit(sessions, media)
    assert admit(sessions, media) == identity
    async def run():
        await asyncio.gather(media.worker.process(identity), media.worker.process(identity))
    asyncio.run(run())
    with sessions() as db:
        assert fake.calls == 1
        assert db.get(PostImageGenerationJob, identity).status == "succeeded"
        assert db.scalar(select(func.count()).select_from(ImageGenerationAttempt)) == 1
        assert db.scalar(select(PostMedia)).source_kind == "generated"
        assert db.scalar(select(ImageIntent)).state == "attached"


def test_received_pixels_survive_local_database_failure_without_second_generation(tmp_path, monkeypatch):
    sessions, media, fake = configured(tmp_path)
    identity = admit(sessions, media)
    original = media.worker._persist_result
    calls = []
    def persist(*args):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("simulated database busy")
        return original(*args)
    monkeypatch.setattr(media.worker, "_persist_result", persist)
    asyncio.run(media.worker.process(identity))
    assert all(path.is_file() for path in media.worker._spool_paths(identity))
    asyncio.run(media.worker.process(identity))
    assert fake.calls == 1
    with sessions() as db:
        assert db.get(PostImageGenerationJob, identity).status == "succeeded"


@pytest.mark.parametrize("kind", ["preparation", "unknown"])
def test_failure_counts_actual_submissions_and_unknown_never_resubmits(tmp_path, kind):
    sessions, media, fake = configured(tmp_path)
    fake.error = kind
    identity = admit(sessions, media)
    asyncio.run(media.worker.process(identity))
    asyncio.run(media.worker.process(identity))
    with sessions() as db:
        job = db.get(PostImageGenerationJob, identity)
        assert job.status == ("failed" if kind == "preparation" else "outcome_unknown")
        assert job.attempt_count == (0 if kind == "preparation" else 1)
        assert db.scalar(select(ImageGenerationAttempt)).status == ("released" if kind == "preparation" else "outcome_unknown")
        assert db.scalar(select(PostMedia)) is None
        assert db.get(Post, POST).body
        if kind == "unknown":
            with pytest.raises(ImagePreparationError, match="no_resubmit"):
                media.worker.retry(db, OWNER, POST, "2026-09-30")


@pytest.mark.parametrize("change", ["post", "cancel", "settings"])
def test_late_response_never_attaches_after_source_cancel_or_settings_change(tmp_path, change):
    sessions, media, fake = configured(tmp_path)
    identity = admit(sessions, media)
    def mutate():
        with sessions() as db:
            if change == "post":
                db.get(Post, POST).title = "Changed"
            elif change == "cancel":
                media.worker.cancel(db, OWNER, POST)
            else:
                db.get(AgentImageGenerationSetting, CHARACTER).generation_revision += 1
            db.commit()
    fake.after_submit = mutate
    asyncio.run(media.worker.process(identity))
    with sessions() as db:
        assert fake.calls == 1 and db.scalar(select(PostMedia)) is None
        assert db.get(PostImageGenerationJob, identity).status in {"failed", "cancelled"}
        assert db.scalar(select(ImageGenerationAttempt)).status != "released"


def test_empty_scene_keeps_post_without_submitting_and_settings_do_not_backfill(tmp_path):
    sessions, media, fake = configured(tmp_path)
    with sessions() as db:
        assert db.scalar(select(PostImageGenerationJob)) is None
    assert admit(sessions, media, " ") is None
    with sessions() as db:
        assert db.scalar(select(ImageIntent)).state == "blocked"
        assert db.get(Post, POST).body and fake.calls == 0


def test_reference_off_does_not_read_override_card_or_profile(tmp_path, monkeypatch):
    sessions, media, _ = configured(tmp_path)
    with sessions() as db:
        character = db.get(Character, CHARACTER)
        setting = db.get(AgentImageGenerationSetting, CHARACTER)
        setting.reference_asset_id = "missing-asset"
        character.avatar_url = "/media/missing.png"
        monkeypatch.setattr(media.assets, "read", lambda *args, **kwargs: pytest.fail("OFF must not read pixels"))
        assert media._reference(db, OWNER, character, setting, False).reason == "disabled"


def test_daily_limit_keeps_blocked_posts_out_of_next_day_backlog(tmp_path,monkeypatch):
    sessions,media,fake=configured(tmp_path,cap=1)
    first=admit(sessions,media)
    with sessions() as db:
        original=db.get(Post,POST)
        second=Post(id="second-image-post",world_id=original.world_id,author_character_id=original.author_character_id,
            author_world_character_id=original.author_world_character_id,author_name=original.author_name,title="Second",body="Body")
        db.add(second);db.flush()
        intent=media.admit_post(db,post=second,owner_id=OWNER,character_id=CHARACTER,
            draft=SimpleNamespace(_image_prompt="reading at a desk",_image_error=None))
        db.commit()
        blocked=db.scalar(select(PostImageGenerationJob).where(PostImageGenerationJob.intent_id==intent.id))
        assert blocked.status=="skipped" and intent.state=="blocked"
        monkeypatch.setattr(media,"quota_day",lambda:"2099-01-02")
    asyncio.run(media.worker.tick())
    with sessions() as db:
        assert fake.calls==0
        assert db.get(PostImageGenerationJob,first).failure_class=="generation_reservation_day_expired"
        assert db.get(PostImageGenerationJob,blocked.id).status=="skipped"
        assert db.scalar(select(func.count()).select_from(PostMedia))==0


def test_explicit_retry_is_idempotent_and_reserves_only_once(tmp_path):
    sessions,media,fake=configured(tmp_path)
    fake.error="preparation";identity=admit(sessions,media)
    asyncio.run(media.worker.process(identity))
    with sessions() as db:
        first=media.worker.retry(db,OWNER,POST,media.quota_day());db.commit()
        second=media.worker.retry(db,OWNER,POST,media.quota_day());db.commit()
        assert first["job_id"]==second["job_id"]==identity
        assert db.scalar(select(func.count()).select_from(ImageGenerationAttempt).where(ImageGenerationAttempt.status=="reserved"))==1
    fake.error=None;asyncio.run(media.worker.process(identity));assert fake.calls==1


def test_two_characters_atomically_share_installation_limit(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from app.domains.social.service.generation_usage import reserve_attempt,set_installation_limit
    sessions,media,_=configured(tmp_path)
    with sessions() as db:
        other=db.scalar(select(Character).where(Character.id!=CHARACTER,Character.owner_id==OWNER))
        assert other is not None
        jobs=[]
        for character in (CHARACTER,other.id):
            job=PostImageGenerationJob(post_id=POST,character_id=character,user_id=OWNER,source="test",status="queued",
                image_model="krea-v2/turbo",image_prompt="scene",prompt_hash="a"*64,key_source="user")
            db.add(job);db.flush();jobs.append((job.id,character))
        set_installation_limit(db,1);db.commit()
    def reserve(pair):
        with sessions() as db:
            try:
                reserve_attempt(db,job_id=pair[0],owner_id=OWNER,character_id=pair[1],character_limit=3,quota_day=media.quota_day())
                db.commit();return "reserved"
            except ImagePreparationError:
                db.rollback();return "blocked"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve,jobs))==["blocked","reserved"]
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(ImageGenerationAttempt).where(ImageGenerationAttempt.status=="reserved"))==1


def test_cancelled_spool_is_deleted_without_reattachment_or_paid_retry(tmp_path):
    sessions,media,fake=configured(tmp_path)
    identity=admit(sessions,media)
    pixels_path,manifest_path=media.worker._spool_paths(identity)
    media.worker.spool.mkdir(parents=True)
    pixels_path.write_bytes(png());manifest_path.write_text('{"content_type":"image/png"}')
    with sessions() as db:
        media.worker.cancel(db,OWNER,POST);db.commit()
    asyncio.run(media.worker.tick())
    assert not pixels_path.exists() and not manifest_path.exists() and fake.calls==0
    with sessions() as db:
        assert db.get(PostImageGenerationJob,identity).status=="cancelled"
        assert db.scalar(select(func.count()).select_from(PostMedia))==0
