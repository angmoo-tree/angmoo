"""World static inputs reach SNS and durable Media; all Providers are injected."""
import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.domains.characters.models import Character, AgentImageGenerationSetting
from app.domains.characters.service.world_image_profiles import available_world_image_models, select_world_image_profile
from app.domains.identity.models import LlmCredential
from app.domains.media.generation_contracts import ImageResult, ImagePreparationError
from app.domains.routines.contracts.activity_policy import ActivityPolicy
from app.domains.routines.models import AgentRun, AgentActivitySetting
from app.runtime.world_configuration.effective_values import character_for_input, setting_for_input
from app.domains.social.models.image_intents import ImageIntent
from app.domains.social.models.posts import Post, PostImageGenerationJob, PostMedia
from app.domains.worlds.models import World, WorldMembership
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
from app.domains.world_characters.service.activity_engines import bind_run
from app.domains.world_characters.service.configuration import effective_configuration
from app.integrations.direct_llm import RunLlmTracker
from app.runtime.autonomous_activity.configuration import configuration_for_activity, accepted_autonomy
from app.runtime.autonomous_activity.execution import context_for_activity_run
from app.runtime.autonomous_activity.feed import FeedLane
from app.runtime.autonomous_activity.inputs import shared_input
from app.runtime.autonomous_activity.provider import ActivityProvider
from app.runtime.media.composition import MediaRuntime
from app.runtime.resident.context import LangGraphResidentContext
from app.runtime.world_characters.management import SqlAlchemyWorldManagementReferences
from world_configuration_fixture_support import seed_configuration_fixture, install_configuration_image_fixture


pytestmark = pytest.mark.usefixtures("deny_external_network")


@pytest.fixture(params=("creation", "legacy_transition"))
def database(tmp_path, request):
    legacy = request.param == "legacy_transition"
    engine = seed_configuration_fixture(tmp_path / "social-input.sqlite", legacy=legacy)
    if legacy:
        from app.runtime.migrations.sqlite_versions import world_configuration_v28
        with engine.begin() as connection:
            before = world_configuration_v28.capture_delta(connection)
            world_configuration_v28.upgrade(connection)
            world_configuration_v28.verify_delta(connection, before)
    yield engine
    engine.dispose()


def world_values(db, suffix, *, name=None, image=False):
    actor = db.get(WorldCharacter, f"config-role-{suffix}")
    stored = db.get(WorldCharacterConfiguration, actor.id)
    stored.profile = {**stored.profile, "display_name": name or f"{suffix.upper()} Bram", "intro": f"World {suffix} intro"}
    stored.settings = {**stored.settings, "personality": f"World {suffix} personality", "speech_style": f"World {suffix} speech",
        "generation_model": "gemini-3.5-flash-lite" if suffix == "a" else "gemini-3.1-flash-lite",
        "active_hours_start": "08:00", "activity_interval_minutes": 45, "max_posts_per_day": 3,
        "image_style": f"World {suffix} watercolor", "appearance_prompt": f"World {suffix} red coat"}
    if image:
        model = install_configuration_image_fixture(db, actor.character_id)
        stored.settings = {**stored.settings, "image_model": model}
    actor.version += 1
    actor.autonomous_enabled = True
    db.commit()
    return actor, effective_configuration(db, world_character_id=actor.id)


def context(db, actor, configuration, *, run_id=None, manual=False):
    cid = actor.character_id
    character = db.get(Character, cid)
    credential = db.get(LlmCredential, f"config-credential-{cid[-1]}")
    now = datetime.now(UTC)
    return LangGraphResidentContext(db=db, run_id=run_id or f"input-run-{cid}", user_id="fixture-owner",
        agent_id="fixture-slot", session_key=f"agent:fixture:{'resident-manual' if manual else 'resident-tick'}:fixture",
        character=character, credential=credential, state=None,
        activity_policy=ActivityPolicy(True, ("post", "reply", "like"), {}, now, "synthetic ready"),
        selected_post_id=None, run_started_at=now,
        input_snapshot={"_world_configuration": configuration.request_snapshot()})


def test_actual_selector_planner_writer_transport_uses_each_accepted_world(database, monkeypatch):
    from app.runtime.autonomous_activity import provider as transport
    calls = []

    async def fake_generate(**kwargs):
        calls.append((kwargs["context"], json.loads(kwargs["user_prompt"])))
        node = kwargs["context"].node
        value = {"selections": []} if node.endswith("TargetSelector") else {"decisions": [], "state_update": None} if node.endswith("ActionPlanner") else {"replies": []}
        return kwargs["validator"](value)

    monkeypatch.setattr(transport, "generate_json", fake_generate)
    monkeypatch.setattr(transport, "_api_key", lambda _: "synthetic-only")
    with Session(database, expire_on_commit=False) as db:
        for suffix in ("a", "b"):
            actor, configuration = world_values(db, suffix)
            ctx = context(db, actor, configuration)
            graph_run = bind_run(db, actor=actor, activity_id=ctx.run_id, configuration=configuration)
            db.commit()
            # Changes after admission must not flow into these model requests.
            common = db.get(Character, actor.character_id)
            common.name, common.personality, common.speech_style = "Live common name", "Live common persona", "Live common speech"
            common.persona_summary = "Live extra summary"
            ctx.credential.model = "Live common model"
            stored = db.get(WorldCharacterConfiguration, actor.id)
            stored.settings = {**stored.settings, "personality": "Later World persona"}
            db.commit()
            payload = shared_input(ctx, actor, db.get(World, actor.world_id))
            assert payload["world_configuration_revision"] == configuration.revision
            assert payload["persona"]["name"] == graph_run.result["name_binding"]["actor_display_name"] == f"{suffix.upper()} Bram"
            assert "legacy_persona_summary_extra" not in payload["persona"]
            before = len(db.dirty)
            gateway = ActivityProvider(ctx, RunLlmTracker(max_calls=3))

            async def exercise():
                await gateway.select(lane="feed", context=payload, candidates=[], limit=1)
                await gateway.plan(lane="feed", context=payload, candidates=[])
                await gateway.write(lane="feed", context=payload, assignments=[])

            asyncio.run(exercise())
            assert len(db.dirty) == before == 0
            assert common.personality == "Live common persona"
    assert len(calls) == 6
    for call, payload in calls:
        suffix = payload["context"]["world_id"][-1]
        assert call.model == ("gemini-3.5-flash-lite" if suffix == "a" else "gemini-3.1-flash-lite")
        assert payload["context"]["persona"]["personality"] == f"World {suffix} personality"
        assert payload["context"]["persona"]["speech_style"] == f"World {suffix} speech"
        assert "Live common" not in json.dumps(payload)


def test_activity_binding_and_recovery_retain_original_configuration(database):
    with Session(database, expire_on_commit=False) as db:
        actor, configuration = world_values(db, "a", name="Accepted Bram")
        original = context(db, actor, configuration, run_id="original-activity")
        db.add(AgentRun(id=original.run_id, user_id=original.user_id, character_id=actor.character_id,
            agent_id=original.agent_id, session_key=original.session_key, input_snapshot=original.input_snapshot))
        graph = bind_run(db, actor=actor, activity_id=original.run_id, configuration=configuration)
        db.commit()
        stored = db.get(WorldCharacterConfiguration, actor.id)
        stored.profile = {**stored.profile, "display_name": "New Bram"}
        stored.settings = {**stored.settings, "generation_model": "gemini-3.1-flash-lite", "personality": "New personality"}
        actor.version += 1
        db.commit()
        new_configuration = effective_configuration(db, world_character_id=actor.id)
        repeat = bind_run(db, actor=actor, activity_id=original.run_id, configuration=new_configuration)
        assert repeat.result["name_binding"]["actor_display_name"] == "Accepted Bram"
        fresh = context(db, actor, new_configuration, run_id="new-recovery-lease")
        recovered = context_for_activity_run(fresh, graph)
        assert recovered.run_id == original.run_id and fresh.run_id == "new-recovery-lease"
        assert recovered.generation_model == "gemini-3.5-flash-lite"
        assert configuration_for_activity(recovered, actor).request_snapshot() == configuration.request_snapshot()
        assert character_for_input(recovered.character, recovered.input_snapshot).personality == "World a personality"
        assert new_configuration.profile.display_name == "New Bram"


def test_gateway_writer_retains_accepted_default_model_after_credential_edit(database, monkeypatch):
    from pydantic import SecretStr
    from app.runtime.resident import writing
    calls = []

    class Gateway:
        def __init__(self, **kwargs):
            pass

        async def run_agent(self, **kwargs):
            calls.append(kwargs)
            return {"status": "completed", "text": '{"body":"synthetic"}'}

    monkeypatch.setattr(writing, "OpenClawGatewayClient", Gateway)
    monkeypatch.setattr(writing.settings, "OPENCLAW_GATEWAY_TOKEN", SecretStr("synthetic-controlled-token"))
    with Session(database, expire_on_commit=False) as db:
        actor, configuration = world_values(db, "a")
        stored = db.get(WorldCharacterConfiguration, actor.id)
        stored.settings = {**stored.settings, "generation_model": None}
        actor.version += 1
        db.commit()
        configuration = effective_configuration(db, world_character_id=actor.id)
        ctx = context(db, actor, configuration)
        snapshot = {**ctx.input_snapshot, "_generation_model": "gemini-3.5-flash-lite"}
        ctx.credential.model = "gemini-3.1-flash-lite"
        result = writing._run_composition_gateway(run=SimpleNamespace(
            id="accepted-default-writer", agent_id=ctx.agent_id, character_id=actor.character_id,
            tool_auth_key="synthetic-only", session_key=ctx.session_key, gateway_result={}, input_snapshot=snapshot),
            credential=ctx.credential, session_key=ctx.session_key, kind="create_post", brief="synthetic brief",
            target_post_id=None, prompt="synthetic prompt", stream_params={})
        assert result["status"] == "completed"
        assert len(calls) == 1 and calls[0]["model"] == "gemini-3.5-flash-lite"
        assert calls[0]["auth_profile_id"] == ctx.credential.auth_profile_id
        assert calls[0]["tool_choice"] == "none"


def test_world_static_views_do_not_dirty_identity_or_learned_facts(database):
    with Session(database, expire_on_commit=False) as db:
        actor, configuration = world_values(db, "a")
        ctx = context(db, actor, configuration)
        character = db.get(Character, actor.character_id)
        setting = db.get(AgentActivitySetting, actor.character_id)
        before = (character.name, character.personality, setting.auto_enabled, setting.activity_interval_minutes, setting.tendency_summary)
        model_character = character_for_input(character, ctx.input_snapshot)
        model_setting = setting_for_input(setting, ctx.input_snapshot, character_id=character.id)
        assert model_character.name == "A Bram" and model_character.personality == "World a personality"
        assert model_setting.activity_interval_minutes == 45 and model_setting.max_posts_per_day == 3
        assert model_setting.tendency_summary == setting.tendency_summary
        assert not db.dirty
        assert before == (character.name, character.personality, setting.auto_enabled, setting.activity_interval_minutes, setting.tendency_summary)
        with pytest.raises((TypeError, AttributeError)):
            model_character.values["name"] = "mutation"
        other = db.get(WorldCharacter, "config-role-b")
        with pytest.raises(ValueError, match="snapshot_scope_invalid"):
            configuration_for_activity(ctx, other)


@pytest.mark.parametrize("manual", [False, True])
def test_feed_retains_accepted_on_or_manual_but_current_membership_is_required(database, monkeypatch, manual):
    from app.domains.social.service import recommendation_topics
    from app.domains.social.exceptions import WorldFeedReadinessError
    monkeypatch.setattr(settings, "DAILY_PREPARATION_ENABLED", True)
    monkeypatch.setattr(recommendation_topics, "character_topics_usable", lambda *args, **kwargs: True)
    with Session(database, expire_on_commit=False) as db:
        actor, configuration = world_values(db, "a")
        if manual:
            configuration = replace(configuration, autonomous_enabled=False)
        ctx = context(db, actor, configuration, manual=manual)
        actor.autonomous_enabled = False
        db.commit()
        assert accepted_autonomy(ctx, actor)
        lane = FeedLane(ctx, actor=actor, lane="feed", tracker=RunLlmTracker(max_calls=0), hybrid_service=None, guard=lambda _: None)
        profile = lane.profile()
        assert profile.world_character.autonomous_enabled and profile.character.name == "A Bram"
        assert actor.autonomous_enabled is False and not db.dirty
        membership = db.get(WorldMembership, actor.membership_id)
        membership.status = "left"
        db.commit()
        with pytest.raises(WorldFeedReadinessError, match="world_scope_not_ready"):
            lane.profile()


def png():
    buffer = BytesIO()
    Image.new("RGB", (8, 8), "blue").save(buffer, "PNG")
    return buffer.getvalue()


class FakeImages:
    def __init__(self):
        self.requests = []

    async def generate(self, request, key, reference, *, on_receipt=None, receipt=None, on_submit=None):
        assert key is None and reference is None
        if receipt is None:
            if on_submit:
                await on_submit()
            self.requests.append(request)
        if on_receipt:
            await on_receipt("synthetic-receipt")
        return ImageResult(png(), "image/png", receipt="synthetic-receipt")


def test_actual_image_admission_and_worker_retain_frozen_world_values(database, tmp_path):
    sessions = sessionmaker(database, expire_on_commit=False)
    fake = FakeImages()
    media = MediaRuntime(sessions, SimpleNamespace(media_root_path=tmp_path / "media"), clients={"comfyui": fake})
    with sessions() as db:
        actor, configuration = world_values(db, "a", image=True)
        media.limits.write(db, 4, expected_revision=0)
        # The World selects its saved model even when a different connection
        # profile is active in the independent common image settings.
        image_setting = db.get(AgentImageGenerationSetting, actor.character_id)
        profiles = json.loads(image_setting.generation_profiles_json)
        profile = profiles["comfyui:fixture-workflow:"]
        profile["active"] = False
        profiles["comfyui:other-workflow:"] = {**profile, "active": True}
        image_setting.generation_profiles_json = json.dumps(profiles)
        image_setting.generation_model = "other-workflow"
        post = Post(id="world-a-image-post", world_id=actor.world_id, author_world_character_id=actor.id,
            author_character_id=actor.character_id, author_name=configuration.profile.display_name, title="A post", body="A body")
        db.add(post)
        db.flush()
        snapshot = {"_world_configuration": configuration.request_snapshot()}
        intent = media.admit_post(db, post=post, owner_id="fixture-owner", character_id=actor.character_id,
            draft=SimpleNamespace(_image_prompt="reading at a desk", _image_error=None), input_snapshot=snapshot)
        db.commit()
        assert intent.state == "queued"
        stored = db.get(WorldCharacterConfiguration, actor.id)
        stored.settings = {**stored.settings, "image_style": "Later style", "appearance_prompt": "Later appearance", "image_model": None}
        db.commit()
        job = db.scalar(select(PostImageGenerationJob).where(PostImageGenerationJob.intent_id == intent.id))
        job_id = job.id
        assert json.loads(intent.request_json)["positive"] == "World a watercolor, World a red coat, reading at a desk"
        assert json.loads(intent.request_json)["model"] != image_setting.generation_model
    asyncio.run(media.worker.process(job_id))
    asyncio.run(media.worker.process(job_id))
    assert len(fake.requests) == 1
    assert fake.requests[0].model == "fixture-workflow"
    assert fake.requests[0].positive == "World a watercolor, World a red coat, reading at a desk"
    assert (fake.requests[0].world_id, fake.requests[0].world_character_id, fake.requests[0].world_configuration_revision) == (
        "config-world-a", "config-role-a", configuration.revision)
    with sessions() as db:
        assert db.get(PostImageGenerationJob, job_id).status == "succeeded"
        assert db.scalar(select(PostMedia).where(PostMedia.post_id == "world-a-image-post")).source_kind == "generated"
        assert db.get(WorldCharacter, "config-role-b").autonomous_enabled is False


def test_image_validation_options_and_prepare_use_same_supported_profile(database, tmp_path):
    media = MediaRuntime(sessionmaker(database), SimpleNamespace(media_root_path=tmp_path / "media"), clients={})
    with Session(database, expire_on_commit=False) as db:
        actor, configuration = world_values(db, "a", image=True)
        references = SqlAlchemyWorldManagementReferences()
        references.validate_settings(db, character_id=actor.character_id, changes={"image_model": configuration.settings.image_model})
        options = references.image_model_options(db, character_id=actor.character_id)
        assert options == [{"value": "comfyui:fixture-workflow", "label": "comfyui · fixture-workflow", "enabled": True, "reason": None}]
        request, _, _, _, error = media.prepare_intent(db, "fixture-owner", actor.character_id, "scene", None, configuration=configuration)
        assert error is None and request.model == "fixture-workflow"
        setting = db.get(AgentImageGenerationSetting, actor.character_id)
        profile = json.loads(setting.generation_profiles_json)["comfyui:fixture-workflow:"]
        setting.generation_profiles_json = json.dumps({"comfyui:custom:workflow:": profile})
        assert select_world_image_profile(setting, "comfyui:custom:workflow").model == "custom:workflow"
        assert available_world_image_models(setting)[0]["value"] == "comfyui:custom:workflow"
        profile["connection"]["ready"] = "false"
        setting.generation_profiles_json = json.dumps({"comfyui:custom:workflow:": profile})
        assert available_world_image_models(setting)[0]["enabled"] is False
        setting.generation_profiles_json = json.dumps({"legacy:klein:": {"connection": {"ready": True}},
            "bad": {}, "comfyui:fixture-workflow:": {"connection": {"ready": False}}})
        db.commit()
        assert available_world_image_models(setting)[0]["enabled"] is False
        with pytest.raises(ImagePreparationError, match="connection_unverified"):
            select_world_image_profile(setting, "klein")
        assert media.prepare_intent(db, "fixture-owner", actor.character_id, "scene", None, configuration=configuration)[-1] == "world_image_model_connection_unverified"
        assert not db.dirty


def test_image_foreign_world_or_actor_snapshot_is_rejected_without_intent(database, tmp_path):
    media = MediaRuntime(sessionmaker(database), SimpleNamespace(media_root_path=tmp_path / "media"), clients={})
    with Session(database, expire_on_commit=False) as db:
        actor, configuration = world_values(db, "a", image=True)
        other = db.get(WorldCharacter, "config-role-b")
        post = Post(id="world-b-scope-post", world_id=other.world_id, author_world_character_id=other.id,
            author_character_id=other.character_id, author_name="Bram", title="B", body="B")
        db.add(post)
        db.commit()
        with pytest.raises(ImagePreparationError, match="snapshot_scope_invalid"):
            media.admit_post(db, post=post, owner_id="fixture-owner", character_id=actor.character_id,
                draft=SimpleNamespace(_image_prompt="scene", _image_error=None),
                input_snapshot={"_world_configuration": configuration.request_snapshot()})
        assert list(db.scalars(select(ImageIntent))) == [] and not db.dirty


def test_world_photo_reference_uses_frozen_profile_before_original_card(database, tmp_path):
    import hashlib
    from app.domains.characters.models import CharacterCardSource, AgentCreationDraft
    from app.domains.characters.service.import_configuration import ImportProfile
    root = tmp_path / "media"
    media = MediaRuntime(sessionmaker(database), SimpleNamespace(media_root_path=root, media_url_path="/media"), clients={})
    with Session(database, expire_on_commit=False) as db:
        actor, configuration = world_values(db, "a", image=True)
        photo = root / "characters" / actor.character_id / "world-profile.png"
        photo.parent.mkdir(parents=True)
        photo.write_bytes(png())
        original_card = BytesIO()
        Image.new("RGB", (8, 8), "red").save(original_card, "PNG")
        db.add(AgentCreationDraft(id="original-card-draft", user_id="fixture-owner", model="synthetic", expires_at=datetime.now(UTC)))
        db.flush()
        db.add(CharacterCardSource(id="original-card", owner_id="fixture-owner", character_id=actor.character_id,
            draft_id="original-card-draft", source_format="png", source_bytes=original_card.getvalue(),
            source_sha256=hashlib.sha256(original_card.getvalue()).hexdigest(), parser_version="synthetic", card_version=2))
        db.commit()
        configuration = replace(configuration, profile=ImportProfile.model_validate({**configuration.profile.model_dump(),
            "avatar_url": f"/media/characters/{actor.character_id}/world-profile.png"}))
        character = character_for_input(db.get(Character, actor.character_id), {"_world_configuration": configuration.request_snapshot()})
        image_setting = db.get(AgentImageGenerationSetting, actor.character_id)
        reference = media._reference(db, "fixture-owner", character, image_setting, True, prefer_profile=True)
        original = media._reference(db, "fixture-owner", character, image_setting, True)
        assert reference.source == "profile" and original.source == "card"
        assert reference.digest != original.digest
        assert image_setting.card_asset_id == original.asset_id
