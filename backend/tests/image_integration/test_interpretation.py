import asyncio
from dataclasses import dataclass
from io import BytesIO
from types import SimpleNamespace
import pytest
from PIL import Image
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from app.runtime.persistence.model_registration import register_models
from app.domains.media.service.assets import AssetService
from app.domains.media.service.interpretation import InterpretationService, write_interpretation_settings
from app.domains.media.setting_schemas import InterpretationSettingsWrite
from app.domains.media.models import ImageInterpretation, InterpretationAttempt, InterpretationSetting
from app.domains.identity.models import User
from app.domains.media.interpretation_contracts import parse_analysis
from app.integrations.llm.image_interpretation import GeminiImageInterpreter
from app.providers.contracts import ProviderResponse, ProviderUsage


def pixels():
    output = BytesIO()
    Image.new("RGB", (24, 16), "blue").save(output, "PNG")
    return output.getvalue()


@pytest.fixture
def image_db(tmp_path):
    metadata = register_models()
    engine = create_engine(f"sqlite:///{tmp_path / 'image.sqlite3'}")
    metadata.create_all(engine)
    sessions = sessionmaker(engine)
    with sessions() as db:
        db.add(User(id="owner", email="image@example.test", display_name="Owner"))
        db.commit()
    yield sessions
    engine.dispose()


class FakeInterpreter:
    def __init__(self):
        self.calls = 0
    async def analyze(self, **kwargs):
        self.calls += 1
        await asyncio.sleep(0.02)
        return parse_analysis({"description": "파란색 직사각형", "recall_hint": 123}), {}


def test_shared_one_attempt_and_off_cache(image_db, tmp_path):
    assets = AssetService(tmp_path / "private", lambda *args: None)
    fake = FakeInterpreter()
    service = InterpretationService(image_db, assets, fake, quota_day=lambda dt: dt.date().isoformat())
    with image_db() as db:
        asset = assets.upload(db, owner_id="owner", scope_kind="world", scope_id="world", content_type="image/png", content=pixels())
        asset_id = asset.id
        write_interpretation_settings(db, "owner", InterpretationSettingsWrite(expected_revision=0, enabled=True, daily_limit=1, api_key="fake-only-test-key"))
        db.commit()
    async def run():
        with image_db() as first, image_db() as second:
            left, right = await asyncio.gather(service.interpret(first, "owner", asset_id), service.interpret(second, "owner", asset_id))
            assert left.id == right.id and left.recall_hint is None
    asyncio.run(run())
    with image_db() as db:
        assert fake.calls == 1
        assert db.scalar(select(func.count()).select_from(InterpretationAttempt)) == 1
        setting = db.get(InterpretationSetting, "owner")
        setting.enabled = False
        db.commit()
        assert service.preflight(db, "owner", asset_id)["reason"] == "cached"
        assert service.cached(db, "owner", asset_id).description == "파란색 직사각형"


@pytest.mark.parametrize("model", ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"])
@pytest.mark.parametrize("thinking", ["high", "medium"])
def test_transport_uses_exact_profile_one_image_no_retry(model, thinking):
    class Provider:
        async def generate_json(self, request):
            assert request.model == model and request.thinking_level == thinking
            assert len(request.image_parts) == 1 and request.sdk_attempts == 1
            assert request.image_parts[0].data == pixels()
            assert request.image_parts[0].mime_type == "image/png"
            assert request.image_parts[0].url is None
            return ProviderResponse(text='{"description":"blue"}', parsed=None, usage=ProviderUsage())
    analysis, _ = asyncio.run(GeminiImageInterpreter(Provider()).analyze(
        key="fake", model=model, thinking_level=thinking, content=pixels(), content_type="image/png"))
    assert analysis.description == "blue"


def test_real_gemini_adapter_serializes_bytes_into_one_sdk_image(monkeypatch):
    from app.providers import gemini
    calls = []
    def client(**kwargs):
        assert kwargs["http_options"].retry_options.attempts == 1
        def generate_content(**request):
            calls.append(request)
            parts = request["contents"].parts
            assert len(parts) == 2 and parts[0].text
            assert parts[1].inline_data.data == pixels()
            assert parts[1].inline_data.mime_type == "image/png"
            assert request["config"].thinking_config.thinking_level.value == "MEDIUM"
            return SimpleNamespace(text='{"description":"파란 사각형"}', parsed=None,
                                   candidates=[], usage_metadata=None)
        return SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    monkeypatch.setattr(gemini.genai, "Client", client)
    analysis, _ = asyncio.run(GeminiImageInterpreter().analyze(
        key="fake", model="gemini-3.1-flash-lite", thinking_level="medium",
        content=pixels(), content_type="image/png"))
    assert analysis.description == "파란 사각형" and len(calls) == 1


def test_invalid_hint_does_not_destroy_description():
    assert parse_analysis({"description": "visible", "recall_hint": "x" * 121}).recall_hint is None
    with pytest.raises(ValueError):
        parse_analysis({"description": " "})


def prepared(image_db, tmp_path, interpreter, *, cap=3, scopes=("one",)):
    assets=AssetService(tmp_path / "private", lambda *args: None)
    service=InterpretationService(image_db,assets,interpreter,quota_day=lambda dt: dt.date().isoformat())
    with image_db() as db:
        identities=[assets.upload(db,owner_id="owner",scope_kind="thread",scope_id=scope,content_type="image/png",content=pixels()).id for scope in scopes]
        write_interpretation_settings(db,"owner",InterpretationSettingsWrite(expected_revision=0,enabled=True,daily_limit=cap,api_key="fake-only"))
        db.commit()
    return assets, service, identities


def test_consumer_cancellation_does_not_cancel_shared_analysis(image_db,tmp_path):
    fake=FakeInterpreter(); _,service,(identity,)=prepared(image_db,tmp_path,fake)
    async def scenario():
        with image_db() as first, image_db() as second:
            cancelled=asyncio.create_task(service.interpret(first,"owner",identity))
            await asyncio.sleep(.005)
            joined=asyncio.create_task(service.interpret(second,"owner",identity))
            cancelled.cancel()
            with pytest.raises(asyncio.CancelledError): await cancelled
            assert (await joined).status == "succeeded"
    asyncio.run(scenario())
    assert fake.calls == 1


def test_scope_isolation_and_owner_quota(image_db,tmp_path):
    fake=FakeInterpreter();_,service,identities=prepared(image_db,tmp_path,fake,cap=1,scopes=("one","two"))
    async def scenario():
        with image_db() as db:
            await service.interpret(db,"owner",identities[0])
            assert service.cached(db,"owner",identities[1]) is None
            assert service.preflight(db,"owner",identities[1])["reason"] == "interpretation_daily_limit_reached"
    asyncio.run(scenario());assert fake.calls == 1


def test_received_analysis_recovers_db_failure_without_second_api(image_db,tmp_path,monkeypatch):
    fake=FakeInterpreter();_,service,(identity,)=prepared(image_db,tmp_path,fake)
    original=service._persist_received; calls=[]
    def persist(*args):
        calls.append(1)
        if len(calls)==1: raise RuntimeError("simulated busy")
        return original(*args)
    monkeypatch.setattr(service,"_persist_received",persist)
    async def scenario():
        with image_db() as db:
            assert (await service.interpret(db,"owner",identity)).status == "succeeded"
    asyncio.run(scenario());assert fake.calls==1 and len(calls)==2
    assert not list(service.spool.glob("*.json"))


@pytest.mark.parametrize("error",[ValueError("invalid schema"),TimeoutError("uncertain")])
def test_failed_analysis_requires_explicit_retry_unknown_never_resubmits(image_db,tmp_path,error):
    class Failing(FakeInterpreter):
        async def analyze(self,**kwargs):
            self.calls+=1
            raise error
    fake=Failing();_,service,(identity,)=prepared(image_db,tmp_path,fake)
    from app.domains.media.generation_contracts import ImagePreparationError
    async def scenario():
        with image_db() as db:
            with pytest.raises(ImagePreparationError): await service.interpret(db,"owner",identity)
            with pytest.raises(ImagePreparationError): await service.interpret(db,"owner",identity)
            assert fake.calls==1
            if isinstance(error,TimeoutError):
                with pytest.raises(ImagePreparationError): await service.interpret(db,"owner",identity,retry_failed=True)
                assert fake.calls==1
            else:
                service.interpreter=FakeInterpreter()
                assert (await service.interpret(db,"owner",identity,retry_failed=True)).status=="succeeded"
    asyncio.run(scenario())


def test_settings_changed_during_analysis_discards_late_result(image_db,tmp_path):
    class Changed(FakeInterpreter):
        async def analyze(self,**kwargs):
            with image_db() as other:
                other.get(InterpretationSetting,"owner").enabled=False
                other.commit()
            return parse_analysis({"description":"late"}),{}
    _,service,(identity,)=prepared(image_db,tmp_path,Changed())
    from app.domains.media.generation_contracts import ImagePreparationError
    async def scenario():
        with image_db() as db:
            with pytest.raises(ImagePreparationError,match="settings_changed"): await service.interpret(db,"owner",identity)
            assert service.cached(db,"owner",identity) is None
    asyncio.run(scenario())
