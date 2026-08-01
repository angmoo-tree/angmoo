import asyncio
import base64
from datetime import UTC, datetime
from io import BytesIO
import json
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest
from PIL import Image
from pydantic import SecretStr, ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.image_generation import (
    POLLINATIONS_IMAGE_MODEL_FLUX_KLEIN,
    POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL,
    POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT,
    POLLINATIONS_IMAGE_MODEL_ZIMAGE,
    REPLICATE_IMAGE_MODEL_PRUNA_EDIT,
    REPLICATE_IMAGE_MODEL_ZIMAGE_TURBO_LORA,
)
from app.core.config import settings
from app.cruds import agents as agent_crud
from app.services import (
    agents as agent_service,
    image_prompt_safety,
    pollinations_image,
    post_image_generation,
    profile_media,
    service_image_key,
)


def test_image_generation_setting_update_bounds() -> None:
    valid = schemas.AgentImageGenerationSettingUpdate(max_images_per_day=20)
    assert valid.max_images_per_day == 20

    with pytest.raises(ValidationError):
        schemas.AgentImageGenerationSettingUpdate(max_images_per_day=21)

    with pytest.raises(ValidationError):
        schemas.AgentImageGenerationSettingUpdate(pollinations_image_model="other")  # type: ignore[arg-type]

    zimage = schemas.AgentImageGenerationSettingUpdate(
        pollinations_image_model="zimage"
    )
    assert zimage.pollinations_image_model == "zimage"

    flux = schemas.AgentImageGenerationSettingUpdate(
        pollinations_image_model="flux"
    )
    assert flux.pollinations_image_model == "flux"

    pruna = schemas.AgentImageGenerationSettingUpdate(
        pollinations_image_model="p-image-edit"
    )
    assert pruna.pollinations_image_model == "p-image-edit"

    replicate_pruna = schemas.AgentImageGenerationSettingUpdate(
        pollinations_image_model=REPLICATE_IMAGE_MODEL_PRUNA_EDIT
    )
    assert replicate_pruna.pollinations_image_model == REPLICATE_IMAGE_MODEL_PRUNA_EDIT


def test_service_image_model_uses_operation_setting_and_user_model_stays_per_agent() -> None:
    setting = SimpleNamespace(
        pollinations_image_model=POLLINATIONS_IMAGE_MODEL_ZIMAGE,
    )
    db = SimpleNamespace(
        get=lambda _model, _key: models.SiteOperationSetting(
            key="pollinations_free_image_model",
            value=POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL,
        )
    )

    assert (
        post_image_generation._image_model_for_key_source(
            setting,
            "service",
            db=db,
        )
        == POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL
    )
    assert (
        post_image_generation._image_model_for_key_source(
            setting,
            "user",
            db=db,
        )
        == POLLINATIONS_IMAGE_MODEL_ZIMAGE
    )


def test_first_greeting_image_mode_uses_first_greeting_identity_model() -> None:
    assert (
        post_image_generation._image_llm_model_for_writing_mode("first_greeting")
        == "gemini-3.1-flash-lite"
    )


def test_image_generation_setting_encrypts_key() -> None:
    engine = create_engine("sqlite:///:memory:")
    models.Character.__table__.create(engine)
    models.AgentImageGenerationSetting.__table__.create(engine)

    with Session(engine) as db:
        setting = agent_crud.ensure_image_generation_setting(db, "char-1")
        updated = agent_crud.update_image_generation_setting(
            db,
            setting,
            schemas.AgentImageGenerationSettingUpdate(pollinations_api_key="test-key"),
        )

        assert updated.key_fingerprint
        assert updated.encrypted_pollinations_api_key
        assert "test-key" not in updated.encrypted_pollinations_api_key

        cleared = agent_crud.update_image_generation_setting(
            db,
            updated,
            schemas.AgentImageGenerationSettingUpdate(clear_pollinations_api_key=True),
        )
        assert cleared.encrypted_pollinations_api_key is None
        assert cleared.key_fingerprint is None


def test_image_generation_setting_mode_sync_and_preserve_key() -> None:
    engine = create_engine("sqlite:///:memory:")
    models.Character.__table__.create(engine)
    models.AgentImageGenerationSetting.__table__.create(engine)

    with Session(engine) as db:
        setting = agent_crud.ensure_image_generation_setting(db, "char-1")
        assert setting.image_key_mode == "disabled"
        assert setting.image_generation_enabled is False

        user_mode = agent_crud.update_image_generation_setting(
            db,
            setting,
            schemas.AgentImageGenerationSettingUpdate(
                image_key_mode="user",
                pollinations_api_key="test-key",
            ),
        )
        assert user_mode.image_key_mode == "user"
        assert user_mode.image_generation_enabled is True
        assert user_mode.encrypted_pollinations_api_key

        disabled = agent_crud.update_image_generation_setting(
            db,
            user_mode,
            schemas.AgentImageGenerationSettingUpdate(image_key_mode="disabled"),
        )
        assert disabled.image_key_mode == "disabled"
        assert disabled.image_generation_enabled is False
        assert disabled.encrypted_pollinations_api_key

        cleared = agent_crud.update_image_generation_setting(
            db,
            disabled,
            schemas.AgentImageGenerationSettingUpdate(
                image_key_mode="user",
                clear_pollinations_api_key=True,
            ),
        )
        assert cleared.image_key_mode == "disabled"
        assert cleared.image_generation_enabled is False
        assert cleared.encrypted_pollinations_api_key is None


def test_service_image_key_helper_accepts_raw_key(monkeypatch) -> None:
    service_image_key._SERVICE_KEY_CACHE.clear()
    monkeypatch.setattr(settings, "POLLINATIONS_SERVICE_IMAGE_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "POLLINATIONS_SERVICE_IMAGE_API_KEY",
        SecretStr("service-key"),
    )

    assert service_image_key.get_service_image_api_key() == "service-key"
    assert service_image_key.is_service_image_available()


def test_service_image_key_helper_decrypts_envelope(monkeypatch) -> None:
    service_image_key._SERVICE_KEY_CACHE.clear()
    monkeypatch.setattr(settings, "POLLINATIONS_SERVICE_IMAGE_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "POLLINATIONS_SERVICE_IMAGE_API_KEY",
        SecretStr("oci-kms-v1:encrypted"),
    )
    monkeypatch.setattr(
        service_image_key.security,
        "decrypt_secret",
        lambda value: "decrypted-service-key",
    )

    assert service_image_key.get_service_image_api_key() == "decrypted-service-key"
    assert service_image_key.is_service_image_available()


def test_service_image_key_helper_hides_invalid_envelope(monkeypatch) -> None:
    service_image_key._SERVICE_KEY_CACHE.clear()
    monkeypatch.setattr(settings, "POLLINATIONS_SERVICE_IMAGE_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "POLLINATIONS_SERVICE_IMAGE_API_KEY",
        SecretStr("oci-kms-v1:invalid"),
    )

    def fail_decrypt(_value: str) -> str:
        raise ValueError("bad envelope")

    monkeypatch.setattr(service_image_key.security, "decrypt_secret", fail_decrypt)

    assert service_image_key.get_service_image_api_key() is None
    assert not service_image_key.is_service_image_available()


def test_initial_image_setting_uses_service_key_availability(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    models.Character.__table__.create(engine)
    models.AgentImageGenerationSetting.__table__.create(engine)

    with Session(engine) as db:
        monkeypatch.setattr(
            agent_service.service_image_key,
            "is_service_image_available",
            lambda: True,
        )
        agent_service._ensure_initial_image_settings(db, "char-service")
        service_setting = agent_crud.get_image_generation_setting(db, "char-service")
        assert service_setting is not None
        assert service_setting.image_key_mode == "service"
        assert service_setting.image_generation_enabled is True

        monkeypatch.setattr(
            agent_service.service_image_key,
            "is_service_image_available",
            lambda: False,
        )
        agent_service._ensure_initial_image_settings(db, "char-disabled")
        disabled_setting = agent_crud.get_image_generation_setting(db, "char-disabled")
        assert disabled_setting is not None
        assert disabled_setting.image_key_mode == "disabled"
        assert disabled_setting.image_generation_enabled is False


def test_image_settings_read_uses_global_service_model(monkeypatch) -> None:
    setting = SimpleNamespace(
        character_id="char-service-model",
        image_key_mode="service",
        image_generation_enabled=True,
        max_images_per_day=10,
        pollinations_image_model=POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT,
        seed_image_url="https://angmoo.com/media/seed.webp",
        encrypted_pollinations_api_key="pollinations-encrypted",
        key_fingerprint="pollinations-fingerprint",
        encrypted_replicate_api_token=None,
        replicate_key_fingerprint=None,
        visual_identity_prompt=None,
        visual_identity_source_hash=None,
        updated_at=datetime_utc(),
    )
    checked_models: list[str] = []

    monkeypatch.setattr(
        agent_service,
        "_service_image_quota_read",
        lambda _db, _character_id: {
            "limit": 3,
            "used": 0,
            "remaining": 3,
            "date": "2026-06-15",
        },
    )
    monkeypatch.setattr(
        agent_service.operation_settings,
        "get_pollinations_free_image_model_setting",
        lambda _db: SimpleNamespace(model=REPLICATE_IMAGE_MODEL_ZIMAGE_TURBO_LORA),
    )
    monkeypatch.setattr(
        agent_service.service_image_key,
        "is_service_image_available_for_model",
        lambda model: checked_models.append(model) or True,
    )

    result = agent_service._image_generation_setting_read(SimpleNamespace(), setting)

    assert result.service_image_model == REPLICATE_IMAGE_MODEL_ZIMAGE_TURBO_LORA
    assert result.service_image_model_label == "Replicate · Z-Image Turbo LoRA"
    assert result.service_image_available is True
    assert checked_models == [REPLICATE_IMAGE_MODEL_ZIMAGE_TURBO_LORA]
    assert result.seed_image_url == setting.seed_image_url


def test_image_generation_setting_manual_visual_identity_uses_null_hash() -> None:
    engine = create_engine("sqlite:///:memory:")
    models.Character.__table__.create(engine)
    models.AgentImageGenerationSetting.__table__.create(engine)

    with Session(engine) as db:
        setting = agent_crud.ensure_image_generation_setting(db, "char-1")
        setting.visual_identity_prompt = "auto identity"
        setting.visual_identity_source_hash = "hash"
        updated = agent_crud.update_image_generation_setting(
            db,
            setting,
            schemas.AgentImageGenerationSettingUpdate(
                visual_identity_prompt="manual identity"
            ),
        )

        assert updated.visual_identity_prompt == "manual identity"
        assert updated.visual_identity_source_hash is None


def test_visual_identity_prompt_requires_shared_style_contract() -> None:
    prompt = post_image_generation._visual_identity_system_prompt(
        character=_character_stub()
    ).lower()

    assert "stable visual contract" in prompt
    assert "rendering style:" in prompt
    assert "do not render as:" in prompt
    assert "character identity:" in prompt
    assert "stable traits:" in prompt
    assert "separate physical traits from rendering style" in prompt
    assert "photographic or realistic" in prompt
    assert "conflicting rendering styles" in prompt
    assert "do not name copyrighted franchises or real people" in prompt


def test_pollinations_image_request_uses_bearer_header(monkeypatch) -> None:
    seen: dict[str, object] = {}

    class FakeHeaders:
        def get(self, name: str, default: str = "") -> str:
            return "image/png" if name.lower() == "content-type" else default

    class FakeResponse:
        headers = FakeHeaders()

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            del size
            if getattr(self, "_read", False):
                return b""
            self._read = True
            return b"\x89PNG\r\n\x1a\nimage-bytes"

    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        seen["url"] = getattr(request, "full_url")
        seen["authorization"] = request.get_header("Authorization")  # type: ignore[attr-defined]
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(pollinations_image, "_open_pollinations_request", fake_urlopen)

    generated = asyncio.run(
        pollinations_image.generate_image(
            api_key="sk_test_secret",
            model="zimage",
            prompt="warm morning desk",
            timeout_seconds=1,
        )
    )

    parsed = urlparse(str(seen["url"]))
    query = parse_qs(parsed.query)
    assert generated.content_type == "image/png"
    assert generated.content.startswith(b"\x89PNG")
    assert seen["authorization"] == "Bearer sk_test_secret"
    assert "sk_test_secret" not in str(seen["url"])
    assert "key" not in query
    assert query["model"] == ["zimage"]
    assert query["safe"] == [pollinations_image.POLLINATIONS_SAFE_FILTER]
    assert query["seed"] == ["-1"]
    assert query["nologo"] == ["true"]
    assert "enhance" not in query
    assert "negative_prompt" not in query
    assert "num_inference_steps" not in query
    assert "cfg" not in query
    assert "scheduler" not in query


def test_pollinations_lambda_route_posts_headers_and_restores_image(monkeypatch) -> None:
    seen: dict[str, object] = {}
    image_bytes = b"\xff\xd8image-bytes"

    class FakeHeaders:
        def get(self, name: str, default: str = "") -> str:
            return "application/json" if name.lower() == "content-type" else default

    class FakeResponse:
        headers = FakeHeaders()
        status = 200

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            del size
            if getattr(self, "_read", False):
                return b""
            self._read = True
            return json.dumps(
                {
                    "ok": True,
                    "model": "zimage",
                    "content_type": "image/jpeg",
                    "content_base64": base64.b64encode(image_bytes).decode("ascii"),
                    "status_code": 200,
                    "prompt_length": 16,
                    "url_length": 444,
                }
            ).encode("utf-8")

    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        seen["url"] = getattr(request, "full_url")
        seen["headers"] = dict(request.header_items())  # type: ignore[attr-defined]
        seen["body"] = getattr(request, "data")
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(settings, "POLLINATIONS_IMAGE_RELAY_URL", "https://relay.example.com/")
    monkeypatch.setattr(settings, "POLLINATIONS_IMAGE_RELAY_TOKEN", SecretStr("relay-token"))
    monkeypatch.setattr(pollinations_image, "_open_relay_request", fake_urlopen)

    generated = asyncio.run(
        pollinations_image.generate_image(
            api_key="sk_user_secret",
            model="zimage",
            prompt="warm morning desk",
            reference_image_url="https://angmoo.com/media/seed.webp",
            allow_reference_fallback=False,
            timeout_seconds=1,
            route_mode="lambda",
        )
    )

    headers = {key.lower(): value for key, value in dict(seen["headers"]).items()}
    body = json.loads(bytes(seen["body"]).decode("utf-8"))
    assert generated.content_type == "image/jpeg"
    assert generated.content == image_bytes
    assert seen["url"] == "https://relay.example.com/"
    assert headers["authorization"] == "Bearer relay-token"
    assert headers["x-pollinations-api-key"] == "sk_user_secret"
    assert body["model"] == "zimage"
    assert body["prompt"] == "warm morning desk"
    assert body["image"] == "https://angmoo.com/media/seed.webp"
    assert body["safe"] == pollinations_image.POLLINATIONS_SAFE_FILTER
    assert body["nologo"] is True
    assert "headers" not in body
    assert "api_key" not in body
    assert "sk_user_secret" not in str(body)


def test_pollinations_lambda_route_preserves_provider_failure(monkeypatch) -> None:
    canary = "phase7-relay-body-canary-71ad"

    class FakeHeaders:
        def get(self, name: str, default: str = "") -> str:
            return "application/json" if name.lower() == "content-type" else default

    class FakeResponse:
        headers = FakeHeaders()
        status = 200

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            del size
            if getattr(self, "_read", False):
                return b""
            self._read = True
            return json.dumps(
                {
                    "ok": False,
                    "failure_class": "http_400",
                    "status_code": 400,
                    "response_body_preview": (
                        '{"error":"Something was wrong with the input data",'
                        f'"reflected":"{canary}"}}'
                    ),
                    "response_content_type": "application/json",
                    "prompt_length": 17,
                    "url_length": 555,
                    "safe_filter": pollinations_image.POLLINATIONS_SAFE_FILTER,
                    "elapsed_ms": 1234,
                }
            ).encode("utf-8")

    monkeypatch.setattr(settings, "POLLINATIONS_IMAGE_RELAY_URL", "https://relay.example.com/")
    monkeypatch.setattr(settings, "POLLINATIONS_IMAGE_RELAY_TOKEN", SecretStr("relay-token"))
    monkeypatch.setattr(
        pollinations_image,
        "_open_relay_request",
        lambda *_args, **_kwargs: FakeResponse(),
    )

    with pytest.raises(pollinations_image.PollinationsImageError) as raised:
        asyncio.run(
            pollinations_image.generate_image(
                api_key="sk_user_secret",
                model="zimage",
                prompt="warm morning desk",
                timeout_seconds=1,
                route_mode="lambda",
            )
        )

    exc = raised.value
    assert exc.failure_class == "http_400"
    assert exc.status_code == 400
    assert exc.response_body_preview is None
    assert exc.response_content_type == "application/json"
    assert exc.request_url_length == 555
    assert exc.prompt_length == 17
    assert exc.safe_filter == pollinations_image.POLLINATIONS_SAFE_FILTER
    assert exc.relay_elapsed_ms == 1234
    assert exc.diagnostic_hint == "provider_input_or_model_policy"
    assert "sk_user_secret" not in str(exc)
    assert "sk_user_secret" not in str(exc.__dict__)
    assert canary not in str(exc)
    assert canary not in repr(exc.__dict__)


def test_pollinations_lambda_route_can_omit_safe_filter_for_manual_probe(monkeypatch) -> None:
    seen: dict[str, object] = {}
    image_bytes = b"\xff\xd8image-bytes"

    class FakeHeaders:
        def get(self, name: str, default: str = "") -> str:
            return "application/json" if name.lower() == "content-type" else default

    class FakeResponse:
        headers = FakeHeaders()
        status = 200

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            del size
            if getattr(self, "_read", False):
                return b""
            self._read = True
            return json.dumps(
                {
                    "ok": True,
                    "content_type": "image/jpeg",
                    "content_base64": base64.b64encode(image_bytes).decode("ascii"),
                }
            ).encode("utf-8")

    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        seen["body"] = getattr(request, "data")
        return FakeResponse()

    monkeypatch.setattr(settings, "POLLINATIONS_IMAGE_RELAY_URL", "https://relay.example.com/")
    monkeypatch.setattr(settings, "POLLINATIONS_IMAGE_RELAY_TOKEN", SecretStr("relay-token"))
    monkeypatch.setattr(pollinations_image, "_open_relay_request", fake_urlopen)

    generated = asyncio.run(
        pollinations_image.generate_image(
            api_key="sk_user_secret",
            model="zimage",
            prompt="warm morning desk",
            timeout_seconds=1,
            route_mode="lambda",
            safe_filter=None,
        )
    )

    body = json.loads(bytes(seen["body"]).decode("utf-8"))
    assert generated.content == image_bytes
    assert "safe" not in body
    assert generated.safe_filter is None


def test_pollinations_image_edit_request_includes_reference_image(monkeypatch) -> None:
    seen: dict[str, object] = {}

    class FakeHeaders:
        def get(self, name: str, default: str = "") -> str:
            return "image/jpeg" if name.lower() == "content-type" else default

    class FakeResponse:
        headers = FakeHeaders()

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            del size
            if getattr(self, "_read", False):
                return b""
            self._read = True
            return b"\xff\xd8image-bytes"

    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        seen["url"] = getattr(request, "full_url")
        seen["authorization"] = request.get_header("Authorization")  # type: ignore[attr-defined]
        return FakeResponse()

    monkeypatch.setattr(pollinations_image, "_open_pollinations_request", fake_urlopen)

    generated = asyncio.run(
        pollinations_image.generate_image(
            api_key="sk_test_secret",
            model=POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT,
            prompt="Place the character at a desk.",
            reference_image_url="https://angmoo.com/media/seed.webp",
            allow_reference_fallback=False,
            timeout_seconds=1,
        )
    )

    parsed = urlparse(str(seen["url"]))
    query = parse_qs(parsed.query)
    assert generated.fallback_used is False
    assert seen["authorization"] == "Bearer sk_test_secret"
    assert query["model"] == ["p-image-edit"]
    assert query["image"] == ["https://angmoo.com/media/seed.webp"]
    assert "quality" not in query
    assert "negative_prompt" not in query
    assert "num_inference_steps" not in query
    assert "cfg" not in query


def test_pollinations_http_error_preserves_diagnostic_metadata(
    monkeypatch,
    caplog,
) -> None:
    canary = "phase7-provider-body-canary-9f2e"

    class FakeHeaders:
        def get(self, name: str, default: str = "") -> str:
            if name.lower() == "content-type":
                return "application/json; charset=utf-8"
            if name.lower() == "x-request-id":
                return "req_safe-456"
            return default

    class FakeErrorBody:
        def read(self, _size: int = -1) -> bytes:
            return (
                f'{{"error":"prompt rejected by model policy",'
                f'"reflected":"{canary}"}}'
            ).encode()

        def close(self) -> None:
            return None

    def fake_urlopen(request: object, timeout: int) -> None:
        raise HTTPError(
            getattr(request, "full_url"),
            400,
            "Bad Request",
            FakeHeaders(),
            FakeErrorBody(),
        )

    monkeypatch.setattr(pollinations_image, "_open_pollinations_request", fake_urlopen)

    with pytest.raises(pollinations_image.PollinationsImageError) as raised:
        asyncio.run(
            pollinations_image.generate_image(
                api_key="sk_test_secret",
                model=POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL,
                prompt="warm desk scene",
                timeout_seconds=1,
            )
        )

    exc = raised.value
    assert exc.failure_class == "http_400"
    assert exc.status_code == 400
    assert exc.response_body_preview is None
    assert exc.response_content_type == "application/json"
    assert exc.request_url_length is not None and exc.request_url_length > 0
    assert exc.prompt_length == len("warm desk scene")
    assert exc.reference_sent is False
    assert exc.safe_filter == pollinations_image.POLLINATIONS_SAFE_FILTER
    assert exc.diagnostic_hint == "safe_filter_possible"
    assert exc.provider_request_id == "req_safe-456"
    assert "sk_test_secret" not in str(exc)
    assert "sk_test_secret" not in str(exc.__dict__)
    assert canary not in str(exc)
    assert canary not in repr(exc.__dict__)
    assert canary not in caplog.text


def test_pollinations_failure_diagnostic_hint_classification() -> None:
    assert (
        pollinations_image.classify_failure_diagnostic_hint(
            failure_class="http_400",
            status_code=400,
            response_body_preview='{"message":"Something was wrong with the input data"}',
            response_content_type="application/json",
        )
        == "provider_input_or_model_policy"
    )
    assert (
        pollinations_image.classify_failure_diagnostic_hint(
            failure_class="http_400",
            status_code=400,
            response_body_preview='{"message":"blocked by moderation policy"}',
            response_content_type="application/json",
        )
        == "safe_filter_possible"
    )
    assert (
        pollinations_image.classify_failure_diagnostic_hint(
            failure_class="relay_timeout",
            status_code=None,
            response_body_preview=None,
            response_content_type=None,
        )
        == "relay_infra"
    )


def test_pollinations_image_reference_fallback_can_be_disabled(monkeypatch) -> None:
    calls: list[str | None] = []

    async def fake_request_image(**kwargs):
        calls.append(kwargs["reference_image_url"])
        raise pollinations_image.PollinationsImageError(
            "invalid image",
            failure_class="invalid_image",
        )

    monkeypatch.setattr(pollinations_image, "_request_image", fake_request_image)

    with pytest.raises(pollinations_image.PollinationsImageError):
        asyncio.run(
            pollinations_image.generate_image(
                api_key="sk_test_secret",
                model=POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT,
                prompt="Edit the character.",
                reference_image_url="https://angmoo.com/media/seed.webp",
                allow_reference_fallback=False,
                timeout_seconds=1,
            )
        )

    assert calls == ["https://angmoo.com/media/seed.webp"]


def test_pollinations_image_reference_fallback_remains_for_klein(monkeypatch) -> None:
    calls: list[str | None] = []

    async def fake_request_image(**kwargs):
        calls.append(kwargs["reference_image_url"])
        if kwargs["reference_image_url"] is not None:
            raise pollinations_image.PollinationsImageError(
                "invalid image",
                failure_class="invalid_image",
            )
        return "image/png", b"\x89PNG\r\n\x1a\nimage-bytes"

    monkeypatch.setattr(pollinations_image, "_request_image", fake_request_image)

    generated = asyncio.run(
        pollinations_image.generate_image(
            api_key="sk_test_secret",
            model=POLLINATIONS_IMAGE_MODEL_FLUX_KLEIN,
            prompt="A calm desk scene.",
            reference_image_url="https://angmoo.com/media/seed.webp",
            timeout_seconds=1,
        )
    )

    assert generated.fallback_used is True
    assert calls == ["https://angmoo.com/media/seed.webp", None]


def test_klein_prompt_refiner_includes_body_structure_guidance() -> None:
    character = _character_stub()

    prompt = post_image_generation._image_prompt_system_prompt(
        character=character,
        image_model=POLLINATIONS_IMAGE_MODEL_FLUX_KLEIN,
    )
    lowered = prompt.lower()

    assert "does not add prompt upsampling" in lowered
    assert "detailed and descriptive" in lowered
    assert "important elements first" in lowered
    assert "rendering style from visual_identity" in lowered
    assert "style: followed by that rendering style" in lowered
    assert "main subject, key action or pose" in lowered
    assert "subject, action, context, lighting, materials, composition" in lowered
    assert "post_title and post_body as the final source of truth" in lowered
    assert "writing_brief and active_step only as background" in lowered
    assert "spatial relationships" in lowered
    assert "positively instead of using negative-prompt phrasing" in lowered
    assert "exact wording in double quotes" in lowered
    assert "position, size, style, and color" in lowered
    assert "hex colors" in lowered
    assert "avoid close-up hands" in lowered
    assert "simple limb placement" in lowered
    assert "reference image traits" in lowered
    assert "do not render as constraints" in lowered
    assert "conflicting rendering styles" in lowered
    assert "core elements" not in lowered
    assert "spatial depth" not in lowered
    assert "do not use quality tags" not in lowered
    assert "8k" not in lowered
    assert "masterpiece" not in lowered
    assert "anime style" not in lowered
    assert "human proportions" not in lowered
    assert "five fingers" not in lowered


def test_zimage_prompt_refiner_includes_prompt_enhancer_guidance() -> None:
    prompt = post_image_generation._image_prompt_system_prompt(
        character=_character_stub(),
        image_model=POLLINATIONS_IMAGE_MODEL_ZIMAGE,
    ).lower()

    assert "text-only image model" in prompt
    assert "provider-side style parameters" in prompt
    assert "style: followed by that rendering style" in prompt
    assert "after the style phrase" in prompt
    assert "core elements" in prompt
    assert "post_title and post_body as the final source of truth" in prompt
    assert "writing_brief and active_step only as background" in prompt
    assert "intent, subject, count, action, state" in prompt
    assert "concrete 4:3 visual scene" in prompt
    assert "composition, lighting, materials, color palette, and spatial depth" in prompt
    assert "do not render as constraints" in prompt
    assert "stable physical traits" in prompt
    assert "conflicting rendering styles" in prompt
    assert "position, size, and layout" in prompt
    assert "do not use quality tags" in prompt
    assert "8k" in prompt
    assert "masterpiece" in prompt
    assert "avoid close-up hands" not in prompt
    assert "simple limb placement" not in prompt


def test_flux_schnell_prompt_refiner_includes_concrete_text_to_image_guidance() -> None:
    prompt = post_image_generation._image_prompt_system_prompt(
        character=_character_stub(),
        image_model=POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL,
    ).lower()

    assert "flux schnell" in prompt
    assert "fast text-to-image model" in prompt
    assert "style: followed by that rendering style" in prompt
    assert (
        "style: anime-inspired 2d illustration or polished toon-shaded 3d animation"
        in prompt
    )
    assert "after the style phrase" in prompt
    assert "main subject, action, setting, composition, lighting, color palette, key details" in prompt
    assert "concrete natural-language scene descriptions" in prompt
    assert "provided visual identity's rendering style" in prompt
    assert "do not render as constraints" in prompt
    assert "preserve the physical traits only" in prompt
    assert "animated character portrait" in prompt
    assert "character portrait illustration" in prompt
    assert "post_title and post_body as the final source of truth" in prompt
    assert "do not use quality tags" in prompt
    assert "do not write photo" in prompt
    assert "photorealistic" in prompt
    assert "camera" in prompt
    assert "lens" in prompt
    assert "live-action" in prompt
    assert "explicitly uses those words in its rendering style line" in prompt
    assert "conflicting rendering styles" in prompt
    assert "clean animated character art" in prompt
    assert "stylized illustrated rendering" in prompt
    assert "soft illustrated lighting" in prompt
    assert "exact wording in double quotes" in prompt
    assert "8k" in prompt
    assert "masterpiece" in prompt
    assert "reference image traits" not in prompt
    assert "simple limb placement" not in prompt


def test_pruna_edit_prompt_refiner_includes_editing_guidance() -> None:
    prompt = post_image_generation._image_prompt_system_prompt(
        character=_character_stub(),
        image_model=POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT,
    ).lower()

    assert "image editing instructions" in prompt
    assert "post_title and post_body as the final source of truth" in prompt
    assert "writing_brief and active_step only as background" in prompt
    assert "[modification] [change target] [preservation]" in prompt
    assert "the character from the reference image" in prompt
    assert "preserve the character's face" in prompt
    assert "hairstyle" in prompt
    assert "outfit identity" in prompt
    assert "character identity" in prompt
    assert "art style" in prompt
    assert "visual_identity includes a rendering style line" in prompt
    assert "prioritize the reference image's style" in prompt
    assert "contradictory styles" in prompt
    assert "avoid vague pronouns" in prompt
    assert "exact wording in double quotes" in prompt
    assert "standalone text-to-image prompt" in prompt
    assert "core elements" not in prompt
    assert "does not add prompt upsampling" not in prompt


def test_replicate_models_reuse_existing_prompt_refiners() -> None:
    character = _character_stub()

    assert post_image_generation._image_prompt_system_prompt(
        character=character,
        image_model=REPLICATE_IMAGE_MODEL_PRUNA_EDIT,
    ) == post_image_generation._image_prompt_system_prompt(
        character=character,
        image_model=POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT,
    )
    assert post_image_generation._image_prompt_system_prompt(
        character=character,
        image_model=REPLICATE_IMAGE_MODEL_ZIMAGE_TURBO_LORA,
    ) == post_image_generation._image_prompt_system_prompt(
        character=character,
        image_model=POLLINATIONS_IMAGE_MODEL_ZIMAGE,
    )


def test_klein_compose_prompt_appends_body_structure_suffix() -> None:
    prompt = post_image_generation._compose_pollinations_prompt(
        {"prompt": "soft morning scene"},
        model=POLLINATIONS_IMAGE_MODEL_FLUX_KLEIN,
    )

    assert prompt.startswith("soft morning scene")
    assert prompt.endswith(post_image_generation.KLEIN_BODY_STRUCTURE_PROMPT_SUFFIX)


def test_zimage_compose_prompt_does_not_append_klein_suffix() -> None:
    prompt = post_image_generation._compose_pollinations_prompt(
        {"prompt": "soft morning scene"},
        model=POLLINATIONS_IMAGE_MODEL_ZIMAGE,
    )

    assert prompt == "soft morning scene"


def test_flux_schnell_compose_prompt_does_not_append_klein_suffix() -> None:
    prompt = post_image_generation._compose_pollinations_prompt(
        {"prompt": "soft morning scene"},
        model=POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL,
    )

    assert prompt == "soft morning scene"


def test_pruna_edit_compose_prompt_does_not_append_klein_suffix() -> None:
    prompt = post_image_generation._compose_pollinations_prompt(
        {"prompt": "Modify the reference image."},
        model=POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT,
    )

    assert prompt == "Modify the reference image."


def test_pruna_edit_prepare_skips_without_reference(monkeypatch) -> None:
    setting = SimpleNamespace(
        pollinations_image_model=POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT,
        image_generation_enabled=True,
        encrypted_pollinations_api_key="encrypted-key",
        max_images_per_day=10,
        seed_image_url=None,
        visual_identity_prompt=None,
        visual_identity_source_hash=None,
    )
    character = SimpleNamespace(
        id="char-1",
        avatar_url=None,
        banner_url=None,
    )

    monkeypatch.setattr(
        post_image_generation.agent_crud,
        "get_image_generation_setting",
        lambda _db, _character_id: setting,
    )
    monkeypatch.setattr(post_image_generation, "_daily_image_usage", lambda *_args, **_kwargs: 0)

    result = asyncio.run(
        post_image_generation.prepare_post_image(
            db=SimpleNamespace(),
            character=character,
            credential=SimpleNamespace(),
            run_id="run-1",
            tracker=SimpleNamespace(),
            writing_mode="independent",
            post_title="title",
            post_body="body",
            writing_plan={"mode": "independent"},
            current_time_text="now",
            run_started_at=datetime_utc(),
        )
    )

    assert result.attempt == {
        "status": "skipped",
        "skip_reason": "reference_required",
        "reference_source": None,
        "provider": "pollinations",
        "model": "p-image-edit",
    }


@pytest.mark.parametrize(
    "writing_mode",
    [
        "relationship_point",
        "future_root_post_mode",
    ],
)
def test_prepare_post_image_does_not_skip_new_root_post_modes(
    monkeypatch,
    writing_mode: str,
) -> None:
    setting = SimpleNamespace(
        pollinations_image_model=POLLINATIONS_IMAGE_MODEL_ZIMAGE,
        image_generation_enabled=True,
        encrypted_pollinations_api_key="encrypted-key",
        max_images_per_day=10,
        seed_image_url=None,
        visual_identity_prompt=None,
        visual_identity_source_hash=None,
    )
    character = SimpleNamespace(
        id="char-1",
        owner_id="user-1",
        name="Test Bird",
        one_liner="curious test bird",
        personality="calm",
        worldview="small community nest",
        avatar_url=None,
        banner_url=None,
    )
    captured: dict[str, object] = {}

    async def fake_refine_image_prompt(**_kwargs):
        return {
            "prompt": f"{writing_mode} image prompt",
            "alt_text": f"{writing_mode} image alt",
        }

    async def fake_generate_image(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            content_type="image/png",
            content=b"\x89PNG\r\n\x1a\nimage-bytes",
            fallback_used=False,
        )

    monkeypatch.setattr(
        post_image_generation.agent_crud,
        "get_image_generation_setting",
        lambda _db, _character_id: setting,
    )
    monkeypatch.setattr(post_image_generation, "_daily_image_usage", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(post_image_generation.security, "decrypt_secret", lambda value: value)
    monkeypatch.setattr(
        post_image_generation,
        "_refine_image_prompt",
        fake_refine_image_prompt,
    )
    monkeypatch.setattr(
        post_image_generation.pollinations_image,
        "generate_image",
        fake_generate_image,
    )

    result = asyncio.run(
        post_image_generation.prepare_post_image(
            db=SimpleNamespace(),
            character=character,
            credential=SimpleNamespace(),
            run_id="run-1",
            tracker=SimpleNamespace(),
            writing_mode=writing_mode,
            post_title="title",
            post_body="body",
            writing_plan={"mode": writing_mode},
            current_time_text="now",
            run_started_at=datetime_utc(),
        )
    )

    assert result.ready
    assert result.attempt["status"] == "ready"
    assert result.attempt.get("skip_reason") != "ineligible_writing_mode"
    assert captured["model"] == POLLINATIONS_IMAGE_MODEL_ZIMAGE


def test_prepare_post_image_flux_uses_visual_identity_without_reference(monkeypatch) -> None:
    setting = SimpleNamespace(
        pollinations_image_model=POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL,
        image_generation_enabled=True,
        encrypted_pollinations_api_key="encrypted-key",
        max_images_per_day=10,
        seed_image_url="https://angmoo.com/media/seed.webp",
        visual_identity_prompt="small blue bird with round glasses",
        visual_identity_source_hash=None,
    )
    character = SimpleNamespace(
        id="char-1",
        owner_id="user-1",
        name="Test Bird",
        one_liner="curious test bird",
        personality="calm",
        worldview="small community nest",
        avatar_url=None,
        banner_url=None,
    )
    captured: dict[str, object] = {}

    async def fake_refine_image_prompt(**kwargs):
        captured["refiner_model"] = kwargs["image_model"]
        captured["visual_identity"] = kwargs["visual_identity"]
        return {
            "prompt": "flux refined image prompt",
            "alt_text": "flux image alt",
        }

    async def fake_generate_image(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            content_type="image/png",
            content=b"\x89PNG\r\n\x1a\nimage-bytes",
            fallback_used=False,
        )

    monkeypatch.setattr(
        post_image_generation.agent_crud,
        "get_image_generation_setting",
        lambda _db, _character_id: setting,
    )
    monkeypatch.setattr(post_image_generation, "_daily_image_usage", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(post_image_generation.security, "decrypt_secret", lambda value: value)
    monkeypatch.setattr(post_image_generation, "_refine_image_prompt", fake_refine_image_prompt)
    monkeypatch.setattr(post_image_generation.pollinations_image, "generate_image", fake_generate_image)

    result = asyncio.run(
        post_image_generation.prepare_post_image(
            db=SimpleNamespace(),
            character=character,
            credential=SimpleNamespace(),
            run_id="run-1",
            tracker=SimpleNamespace(),
            writing_mode="independent",
            post_title="title",
            post_body="body",
            writing_plan={"mode": "independent"},
            current_time_text="now",
            run_started_at=datetime_utc(),
        )
    )

    assert result.ready
    assert result.attempt["model"] == POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL
    assert result.attempt["reference_sent"] is False
    assert captured["refiner_model"] == POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL
    assert captured["visual_identity"] == "small blue bird with round glasses"
    assert captured["model"] == POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL
    assert captured["reference_image_url"] is None
    assert captured["allow_reference_fallback"] is False


def test_prepare_post_image_reads_route_mode_at_processing_time(monkeypatch) -> None:
    setting = SimpleNamespace(
        pollinations_image_model=POLLINATIONS_IMAGE_MODEL_ZIMAGE,
        image_generation_enabled=True,
        encrypted_pollinations_api_key="encrypted-key",
        max_images_per_day=10,
        seed_image_url=None,
        visual_identity_prompt=None,
        visual_identity_source_hash=None,
    )
    character = SimpleNamespace(
        id="char-1",
        owner_id="user-1",
        name="Test Bird",
        one_liner="curious test bird",
        personality="calm",
        worldview="small community nest",
        avatar_url=None,
        banner_url=None,
    )
    db = SimpleNamespace(
        get=lambda _model, key: models.SiteOperationSetting(
            key=key,
            value="lambda",
        )
        if key == "pollinations_image_route_mode"
        else None
    )
    captured: dict[str, object] = {}

    async def fake_refine_image_prompt(**_kwargs):
        return {
            "prompt": "route mode prompt",
            "alt_text": "route mode alt",
        }

    async def fake_generate_image(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            content_type="image/png",
            content=b"\x89PNG\r\n\x1a\nimage-bytes",
            fallback_used=False,
        )

    monkeypatch.setattr(
        post_image_generation.agent_crud,
        "get_image_generation_setting",
        lambda _db, _character_id: setting,
    )
    monkeypatch.setattr(post_image_generation, "_daily_image_usage", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(post_image_generation.security, "decrypt_secret", lambda value: value)
    monkeypatch.setattr(post_image_generation, "_refine_image_prompt", fake_refine_image_prompt)
    monkeypatch.setattr(post_image_generation.pollinations_image, "generate_image", fake_generate_image)

    result = asyncio.run(
        post_image_generation.prepare_post_image(
            db=db,
            character=character,
            credential=SimpleNamespace(),
            run_id="run-1",
            tracker=SimpleNamespace(),
            writing_mode="independent",
            post_title="title",
            post_body="body",
            writing_plan={"mode": "independent"},
            current_time_text="now",
            run_started_at=datetime_utc(),
        )
    )

    assert result.ready
    assert captured["route_mode"] == "lambda"
    assert result.attempt["route_mode"] == "lambda"


def test_prepare_post_image_flux_failure_keeps_pollinations_diagnostics(
    monkeypatch,
) -> None:
    setting = SimpleNamespace(
        pollinations_image_model=POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL,
        image_generation_enabled=True,
        encrypted_pollinations_api_key="encrypted-key",
        max_images_per_day=10,
        seed_image_url=None,
        visual_identity_prompt="small blue bird with round glasses",
        visual_identity_source_hash=None,
    )
    character = SimpleNamespace(
        id="char-1",
        owner_id="user-1",
        name="Test Bird",
        one_liner="curious test bird",
        personality="calm",
        worldview="small community nest",
        avatar_url="https://angmoo.com/media/avatar.webp",
        banner_url=None,
    )
    captured: dict[str, object] = {}

    async def fake_refine_image_prompt(**_kwargs):
        return {
            "prompt": "flux refined image prompt",
            "alt_text": "flux image alt",
        }

    async def fake_generate_image(**kwargs):
        captured.update(kwargs)
        raise pollinations_image.PollinationsImageError(
            "bad request",
            failure_class="http_400",
            status_code=400,
            response_body_preview='{"error":"bad prompt"}',
            response_content_type="application/json",
            request_url_length=777,
            prompt_length=len(str(kwargs["prompt"])),
            reference_sent=bool(kwargs["reference_image_url"]),
        )

    monkeypatch.setattr(
        post_image_generation.agent_crud,
        "get_image_generation_setting",
        lambda _db, _character_id: setting,
    )
    monkeypatch.setattr(post_image_generation, "_daily_image_usage", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(post_image_generation.security, "decrypt_secret", lambda value: value)
    monkeypatch.setattr(post_image_generation, "_refine_image_prompt", fake_refine_image_prompt)
    monkeypatch.setattr(post_image_generation.pollinations_image, "generate_image", fake_generate_image)

    result = asyncio.run(
        post_image_generation.prepare_post_image(
            db=SimpleNamespace(),
            character=character,
            credential=SimpleNamespace(),
            run_id="run-1",
            tracker=SimpleNamespace(),
            writing_mode="independent",
            post_title="title",
            post_body="body",
            writing_plan={"mode": "independent"},
            current_time_text="now",
            run_started_at=datetime_utc(),
        )
    )

    attempt = result.attempt
    assert attempt["status"] == "failed"
    assert attempt["failure_class"] == "http_400"
    assert attempt["model"] == POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL
    assert attempt["reference_source"] == "avatar"
    assert attempt["reference_sent"] is False
    assert attempt["key_source"] == "user"
    assert attempt["prompt_hash"] == captured["prompt_hash"]
    assert attempt["prompt_length"] == len("flux refined image prompt")
    assert attempt["pollinations_status_code"] == 400
    assert attempt["pollinations_response_body_preview"] is None
    assert attempt["pollinations_content_type"] == "application/json"
    assert attempt["pollinations_url_length"] == 777
    assert captured["reference_image_url"] is None


def test_local_api_prepare_uses_deterministic_prompt_without_llm(monkeypatch) -> None:
    setting = SimpleNamespace(
        pollinations_image_model=POLLINATIONS_IMAGE_MODEL_ZIMAGE,
        image_generation_enabled=True,
        encrypted_pollinations_api_key="encrypted-key",
        max_images_per_day=10,
        seed_image_url=None,
        visual_identity_prompt="small blue bird with round glasses",
        visual_identity_source_hash=None,
    )
    character = SimpleNamespace(
        id="char-1",
        name="Local Bird",
        avatar_url=None,
        banner_url=None,
    )
    captured: dict[str, object] = {}

    async def fake_generate_image(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            content_type="image/png",
            content=b"\x89PNG\r\n\x1a\nimage-bytes",
            fallback_used=False,
        )

    async def fail_refiner(**_kwargs):
        raise AssertionError("local API image path must not call ImagePromptRefiner")

    async def fail_identity(**_kwargs):
        raise AssertionError("local API image path must not call ImageVisualIdentity")

    monkeypatch.setattr(
        post_image_generation.agent_crud,
        "get_image_generation_setting",
        lambda _db, _character_id: setting,
    )
    monkeypatch.setattr(post_image_generation, "_daily_image_usage", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(post_image_generation.security, "decrypt_secret", lambda value: value)
    monkeypatch.setattr(post_image_generation.pollinations_image, "generate_image", fake_generate_image)
    monkeypatch.setattr(post_image_generation, "_refine_image_prompt", fail_refiner)
    monkeypatch.setattr(post_image_generation, "_ensure_visual_identity", fail_identity)

    result = asyncio.run(
        post_image_generation.prepare_local_api_post_image(
            db=SimpleNamespace(),
            character=character,
            image_prompt="cozy bedtime scene, modest pajamas, warm lamp light",
            run_started_at=datetime_utc(),
        )
    )

    assert result.ready
    assert captured["model"] == POLLINATIONS_IMAGE_MODEL_ZIMAGE
    assert captured["reference_image_url"] is None
    prompt = str(captured["prompt"])
    assert "small blue bird with round glasses" in prompt
    assert "cozy bedtime scene" in prompt
    assert "No sexual content" in prompt
    assert result.alt_text == "Local Bird의 게시글에 첨부된 AI 생성 이미지"


def test_local_api_prepare_reads_route_mode_at_worker_processing_time(monkeypatch) -> None:
    setting = SimpleNamespace(
        pollinations_image_model=POLLINATIONS_IMAGE_MODEL_ZIMAGE,
        image_generation_enabled=True,
        encrypted_pollinations_api_key="encrypted-key",
        max_images_per_day=10,
        seed_image_url=None,
        visual_identity_prompt="small blue bird with round glasses",
        visual_identity_source_hash=None,
    )
    character = SimpleNamespace(
        id="char-1",
        name="Local Bird",
        avatar_url=None,
        banner_url=None,
    )
    db = SimpleNamespace(
        get=lambda _model, key: models.SiteOperationSetting(
            key=key,
            value="lambda",
        )
        if key == "pollinations_image_route_mode"
        else None
    )
    captured: dict[str, object] = {}

    async def fake_generate_image(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            content_type="image/png",
            content=b"\x89PNG\r\n\x1a\nimage-bytes",
            fallback_used=False,
        )

    monkeypatch.setattr(
        post_image_generation.agent_crud,
        "get_image_generation_setting",
        lambda _db, _character_id: setting,
    )
    monkeypatch.setattr(post_image_generation, "_daily_image_usage", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(post_image_generation.security, "decrypt_secret", lambda value: value)
    monkeypatch.setattr(post_image_generation.pollinations_image, "generate_image", fake_generate_image)

    result = asyncio.run(
        post_image_generation.prepare_local_api_post_image(
            db=db,
            character=character,
            image_prompt="cozy bedtime scene, modest pajamas, warm lamp light",
            run_started_at=datetime_utc(),
            post_id="post-1",
            job_id=456,
        )
    )

    assert result.ready
    assert captured["route_mode"] == "lambda"
    assert result.attempt["route_mode"] == "lambda"


def test_local_api_prepare_flux_uses_visual_identity_without_reference(monkeypatch) -> None:
    setting = SimpleNamespace(
        pollinations_image_model=POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL,
        image_generation_enabled=True,
        encrypted_pollinations_api_key="encrypted-key",
        max_images_per_day=10,
        seed_image_url="https://angmoo.com/media/seed.webp",
        visual_identity_prompt="small blue bird with round glasses",
        visual_identity_source_hash=None,
    )
    character = SimpleNamespace(
        id="char-1",
        name="Local Bird",
        avatar_url=None,
        banner_url=None,
    )
    captured: dict[str, object] = {}

    async def fake_generate_image(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            content_type="image/png",
            content=b"\x89PNG\r\n\x1a\nimage-bytes",
            fallback_used=False,
        )

    monkeypatch.setattr(
        post_image_generation.agent_crud,
        "get_image_generation_setting",
        lambda _db, _character_id: setting,
    )
    monkeypatch.setattr(post_image_generation, "_daily_image_usage", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(post_image_generation.security, "decrypt_secret", lambda value: value)
    monkeypatch.setattr(post_image_generation.pollinations_image, "generate_image", fake_generate_image)

    result = asyncio.run(
        post_image_generation.prepare_local_api_post_image(
            db=SimpleNamespace(),
            character=character,
            image_prompt="cozy bedtime scene, modest pajamas, warm lamp light",
            run_started_at=datetime_utc(),
        )
    )

    assert result.ready
    assert captured["model"] == POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL
    assert captured["reference_image_url"] is None
    assert captured["allow_reference_fallback"] is False
    prompt = str(captured["prompt"])
    assert "small blue bird with round glasses" in prompt
    assert "cozy bedtime scene" in prompt


def test_local_api_prepare_failure_propagates_attempt_metadata(monkeypatch) -> None:
    setting = SimpleNamespace(
        pollinations_image_model=POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL,
        image_generation_enabled=True,
        encrypted_pollinations_api_key="encrypted-key",
        max_images_per_day=10,
        seed_image_url="https://angmoo.com/media/seed.webp",
        visual_identity_prompt="small blue bird with round glasses",
        visual_identity_source_hash=None,
    )
    character = SimpleNamespace(
        id="char-1",
        name="Local Bird",
        avatar_url=None,
        banner_url=None,
    )
    captured: dict[str, object] = {}

    async def fake_generate_image(**kwargs):
        captured.update(kwargs)
        raise pollinations_image.PollinationsImageError(
            "bad request",
            failure_class="http_400",
            status_code=400,
            response_body_preview='{"error":"bad prompt"}',
            response_content_type="application/json",
            request_url_length=888,
            prompt_length=len(str(kwargs["prompt"])),
            reference_sent=bool(kwargs["reference_image_url"]),
        )

    monkeypatch.setattr(
        post_image_generation.agent_crud,
        "get_image_generation_setting",
        lambda _db, _character_id: setting,
    )
    monkeypatch.setattr(post_image_generation, "_daily_image_usage", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(post_image_generation.security, "decrypt_secret", lambda value: value)
    monkeypatch.setattr(post_image_generation.pollinations_image, "generate_image", fake_generate_image)

    result = asyncio.run(
        post_image_generation.prepare_local_api_post_image(
            db=SimpleNamespace(),
            character=character,
            image_prompt="cozy bedtime scene, modest pajamas, warm lamp light",
            run_started_at=datetime_utc(),
            post_id="post-1",
            job_id=456,
        )
    )

    attempt = result.attempt
    assert attempt["status"] == "failed"
    assert attempt["failure_class"] == "http_400"
    assert attempt["model"] == POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL
    assert attempt["reference_source"] == "seed"
    assert attempt["reference_sent"] is False
    assert attempt["key_source"] == "user"
    assert attempt["prompt_hash"] == captured["prompt_hash"]
    assert attempt["prompt_length"] == len(str(captured["prompt"]))
    assert attempt["pollinations_status_code"] == 400
    assert attempt["pollinations_response_body_preview"] is None
    assert attempt["pollinations_content_type"] == "application/json"
    assert attempt["pollinations_url_length"] == 888
    assert captured["log_context"]["post_id"] == "post-1"  # type: ignore[index]
    assert captured["log_context"]["job_id"] == 456  # type: ignore[index]


def test_prepare_post_image_service_mode_uses_service_key_and_reservation(
    monkeypatch,
) -> None:
    setting = SimpleNamespace(
        image_key_mode="service",
        pollinations_image_model=POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT,
        image_generation_enabled=True,
        encrypted_pollinations_api_key=None,
        max_images_per_day=0,
        seed_image_url=None,
        visual_identity_prompt="small blue bird with round glasses",
        visual_identity_source_hash=None,
    )
    character = SimpleNamespace(
        id="char-1",
        owner_id="user-1",
        avatar_url=None,
        banner_url=None,
    )
    captured: dict[str, object] = {}

    async def fake_refine_image_prompt(**_kwargs):
        return {
            "prompt": "service refined image prompt",
            "alt_text": "service image alt",
        }

    async def fake_generate_image(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            content_type="image/png",
            content=b"\x89PNG\r\n\x1a\nimage-bytes",
            fallback_used=False,
        )

    def fake_reserve(*_args, **kwargs):
        captured["reservation"] = kwargs
        return SimpleNamespace(id=123)

    monkeypatch.setattr(
        post_image_generation.agent_crud,
        "get_image_generation_setting",
        lambda _db, _character_id: setting,
    )
    monkeypatch.setattr(settings, "POLLINATIONS_SERVICE_IMAGE_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "POLLINATIONS_SERVICE_IMAGE_API_KEY",
        SecretStr("service-key"),
    )
    monkeypatch.setattr(
        settings,
        "POLLINATIONS_SERVICE_IMAGE_MODEL",
        POLLINATIONS_IMAGE_MODEL_ZIMAGE,
    )
    monkeypatch.setattr(
        post_image_generation,
        "_reserve_service_image_quota",
        fake_reserve,
    )
    monkeypatch.setattr(
        post_image_generation,
        "_refine_image_prompt",
        fake_refine_image_prompt,
    )
    monkeypatch.setattr(
        post_image_generation.pollinations_image,
        "generate_image",
        fake_generate_image,
    )

    result = asyncio.run(
        post_image_generation.prepare_post_image(
            db=SimpleNamespace(),
            character=character,
            credential=SimpleNamespace(),
            run_id="run-1",
            tracker=SimpleNamespace(),
            writing_mode="owner_feed_cue",
            post_title="title",
            post_body="body",
            writing_plan={"mode": "owner_feed_cue"},
            current_time_text="now",
            run_started_at=datetime_utc(),
        )
    )

    assert result is not None
    assert result.ready
    assert result.key_source == "service"
    assert result.quota_reservation_id == 123
    assert result.attempt["key_source"] == "service"
    assert captured["api_key"] == "service-key"
    assert captured["model"] == POLLINATIONS_IMAGE_MODEL_ZIMAGE
    assert captured["prompt"] == "service refined image prompt"
    assert captured["reservation"]["user_id"] == "user-1"  # type: ignore[index]
    assert captured["reservation"]["source"] == "resident"  # type: ignore[index]


def test_prepare_post_image_service_failure_keeps_service_mapping_and_diagnostics(
    monkeypatch,
) -> None:
    setting = SimpleNamespace(
        image_key_mode="service",
        pollinations_image_model=POLLINATIONS_IMAGE_MODEL_ZIMAGE,
        image_generation_enabled=True,
        encrypted_pollinations_api_key=None,
        max_images_per_day=0,
        seed_image_url=None,
        visual_identity_prompt="small blue bird with round glasses",
        visual_identity_source_hash=None,
    )
    character = SimpleNamespace(
        id="char-1",
        owner_id="user-1",
        name="Test Bird",
        one_liner="curious test bird",
        personality="calm",
        worldview="small community nest",
        avatar_url=None,
        banner_url=None,
    )

    async def fake_refine_image_prompt(**_kwargs):
        return {
            "prompt": "service refined image prompt",
            "alt_text": "service image alt",
        }

    async def fake_generate_image(**kwargs):
        raise pollinations_image.PollinationsImageError(
            "payment required",
            failure_class="http_402",
            status_code=402,
            response_body_preview='{"error":"budget exhausted"}',
            response_content_type="application/json",
            request_url_length=999,
            prompt_length=len(str(kwargs["prompt"])),
            reference_sent=bool(kwargs["reference_image_url"]),
        )

    monkeypatch.setattr(
        post_image_generation.agent_crud,
        "get_image_generation_setting",
        lambda _db, _character_id: setting,
    )
    monkeypatch.setattr(
        post_image_generation.operation_settings,
        "get_pollinations_free_image_model",
        lambda _db: POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL,
    )
    monkeypatch.setattr(settings, "POLLINATIONS_SERVICE_IMAGE_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "POLLINATIONS_SERVICE_IMAGE_API_KEY",
        SecretStr("service-key"),
    )
    monkeypatch.setattr(
        post_image_generation,
        "_reserve_service_image_quota",
        lambda *_args, **_kwargs: SimpleNamespace(id=321),
    )
    monkeypatch.setattr(
        post_image_generation,
        "_finalize_service_image_quota",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(post_image_generation, "_refine_image_prompt", fake_refine_image_prompt)
    monkeypatch.setattr(post_image_generation.pollinations_image, "generate_image", fake_generate_image)

    result = asyncio.run(
        post_image_generation.prepare_post_image(
            db=SimpleNamespace(),
            character=character,
            credential=SimpleNamespace(),
            run_id="run-1",
            tracker=SimpleNamespace(),
            writing_mode="owner_feed_cue",
            post_title="title",
            post_body="body",
            writing_plan={"mode": "owner_feed_cue"},
            current_time_text="now",
            run_started_at=datetime_utc(),
        )
    )

    attempt = result.attempt
    assert attempt["status"] == "failed"
    assert attempt["failure_class"] == "service_key_budget_exhausted"
    assert attempt["model"] == POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL
    assert attempt["key_source"] == "service"
    assert attempt["quota_reservation_id"] == 321
    assert attempt["prompt_hash"]
    assert attempt["prompt_length"] == len("service refined image prompt")
    assert attempt["pollinations_status_code"] == 402
    assert attempt["pollinations_response_body_preview"] is None
    assert attempt["pollinations_content_type"] == "application/json"
    assert attempt["pollinations_url_length"] == 999


def test_local_api_prepare_requires_manual_visual_identity(monkeypatch) -> None:
    setting = SimpleNamespace(
        pollinations_image_model=POLLINATIONS_IMAGE_MODEL_ZIMAGE,
        image_generation_enabled=True,
        encrypted_pollinations_api_key="encrypted-key",
        max_images_per_day=10,
        seed_image_url=None,
        visual_identity_prompt="auto identity",
        visual_identity_source_hash="reference-hash",
    )
    character = SimpleNamespace(id="char-1", name="Local Bird", avatar_url=None, banner_url=None)
    monkeypatch.setattr(
        post_image_generation.agent_crud,
        "get_image_generation_setting",
        lambda _db, _character_id: setting,
    )

    result = asyncio.run(
        post_image_generation.prepare_local_api_post_image(
            db=SimpleNamespace(),
            character=character,
            image_prompt="peaceful room",
            run_started_at=datetime_utc(),
        )
    )

    assert result.attempt["status"] == "skipped"
    assert result.attempt["skip_reason"] == "visual_identity_required"


def test_image_prompt_safety_allows_plain_bedtime_but_blocks_sexual_modifier() -> None:
    assert (
        image_prompt_safety.unsafe_image_text_reason(
            "cozy bedroom at night, modest pajamas, calm bedtime mood"
        )
        is None
    )
    assert (
        image_prompt_safety.unsafe_image_text_reason(
            "bedroom scene with seductive pose and revealing clothes"
        )
        == "sexual_content"
    )


def test_pruna_edit_prepare_skips_without_public_reference_url(monkeypatch) -> None:
    setting = SimpleNamespace(
        pollinations_image_model=POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT,
        image_generation_enabled=True,
        encrypted_pollinations_api_key="encrypted-key",
        max_images_per_day=10,
        seed_image_url="/media/seed.webp",
        visual_identity_prompt=None,
        visual_identity_source_hash=None,
    )
    character = SimpleNamespace(id="char-1", avatar_url=None, banner_url=None)
    reference = post_image_generation._ReferenceImage(
        source="seed",
        url="/media/seed.webp",
        source_hash="hash",
        llm_part=SimpleNamespace(),
        public_url=None,
    )

    monkeypatch.setattr(
        post_image_generation.agent_crud,
        "get_image_generation_setting",
        lambda _db, _character_id: setting,
    )
    monkeypatch.setattr(post_image_generation, "_daily_image_usage", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(
        post_image_generation,
        "_select_reference_image",
        lambda _character, _setting: reference,
    )

    result = asyncio.run(
        post_image_generation.prepare_post_image(
            db=SimpleNamespace(),
            character=character,
            credential=SimpleNamespace(),
            run_id="run-1",
            tracker=SimpleNamespace(),
            writing_mode="independent",
            post_title="title",
            post_body="body",
            writing_plan={"mode": "independent"},
            current_time_text="now",
            run_started_at=datetime_utc(),
        )
    )

    assert result.attempt["status"] == "skipped"
    assert result.attempt["skip_reason"] == "reference_required"
    assert result.attempt["reference_source"] == "seed"
    assert result.attempt["model"] == "p-image-edit"


def test_pruna_edit_prepare_skips_unusable_reference(monkeypatch) -> None:
    setting = SimpleNamespace(
        pollinations_image_model=POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT,
        image_generation_enabled=True,
        encrypted_pollinations_api_key="encrypted-key",
        max_images_per_day=10,
        seed_image_url="https://angmoo.com/media/seed.webp",
        visual_identity_prompt=None,
        visual_identity_source_hash=None,
    )
    character = SimpleNamespace(id="char-1", avatar_url=None, banner_url=None)
    reference = post_image_generation._ReferenceImage(
        source="seed",
        url="https://angmoo.com/media/seed.webp",
        source_hash="hash",
        llm_part=SimpleNamespace(),
        public_url="https://angmoo.com/media/seed.webp",
    )

    async def unusable_identity(**_kwargs):
        return None

    async def fail_refine(**_kwargs):
        raise AssertionError("refiner should not run for unusable edit reference")

    monkeypatch.setattr(
        post_image_generation.agent_crud,
        "get_image_generation_setting",
        lambda _db, _character_id: setting,
    )
    monkeypatch.setattr(post_image_generation, "_daily_image_usage", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(
        post_image_generation,
        "_select_reference_image",
        lambda _character, _setting: reference,
    )
    monkeypatch.setattr(post_image_generation, "_ensure_visual_identity", unusable_identity)
    monkeypatch.setattr(post_image_generation, "_refine_image_prompt", fail_refine)

    result = asyncio.run(
        post_image_generation.prepare_post_image(
            db=SimpleNamespace(),
            character=character,
            credential=SimpleNamespace(),
            run_id="run-1",
            tracker=SimpleNamespace(),
            writing_mode="independent",
            post_title="title",
            post_body="body",
            writing_plan={"mode": "independent"},
            current_time_text="now",
            run_started_at=datetime_utc(),
        )
    )

    assert result.attempt["status"] == "skipped"
    assert result.attempt["skip_reason"] == "reference_unusable"
    assert result.attempt["reference_source"] == "seed"
    assert result.attempt["model"] == "p-image-edit"


def test_pollinations_reference_policy_by_model() -> None:
    reference = post_image_generation._ReferenceImage(
        source="seed",
        url="https://angmoo.com/media/seed.webp",
        source_hash="hash",
        llm_part=SimpleNamespace(),
        public_url="https://angmoo.com/media/seed.webp",
    )

    assert (
        post_image_generation._pollinations_reference_url(
            POLLINATIONS_IMAGE_MODEL_FLUX_KLEIN, reference
        )
        == "https://angmoo.com/media/seed.webp"
    )
    assert (
        post_image_generation._pollinations_reference_url(
            POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT, reference
        )
        == "https://angmoo.com/media/seed.webp"
    )
    assert (
        post_image_generation._pollinations_reference_url(
            POLLINATIONS_IMAGE_MODEL_ZIMAGE, reference
        )
        is None
    )
    assert (
        post_image_generation._pollinations_reference_url(
            POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL, reference
        )
        is None
    )
    assert post_image_generation._requires_pollinations_reference(
        POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT
    )
    assert not post_image_generation._requires_pollinations_reference(
        POLLINATIONS_IMAGE_MODEL_FLUX_KLEIN
    )
    assert not post_image_generation._requires_pollinations_reference(
        POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL
    )
    assert not post_image_generation._allows_reference_fallback(
        POLLINATIONS_IMAGE_MODEL_PRUNA_EDIT
    )
    assert not post_image_generation._allows_reference_fallback(
        POLLINATIONS_IMAGE_MODEL_FLUX_SCHNELL
    )
    assert post_image_generation._allows_reference_fallback(
        POLLINATIONS_IMAGE_MODEL_FLUX_KLEIN
    )


def test_klein_compose_prompt_preserves_suffix_under_length_limit() -> None:
    prompt = post_image_generation._compose_pollinations_prompt(
        {"prompt": "a" * 2200},
        model=POLLINATIONS_IMAGE_MODEL_FLUX_KLEIN,
    )

    assert len(prompt) <= post_image_generation.IMAGE_PROMPT_MAX_LENGTH
    assert prompt.endswith(post_image_generation.KLEIN_BODY_STRUCTURE_PROMPT_SUFFIX)


def test_generated_post_image_saves_webp_under_size(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path))
    content = _png_bytes(size=(1600, 1200), color=(80, 160, 220))

    saved = profile_media.save_generated_post_image_bytes(
        post_id="post-test",
        content_type="image/png",
        content=content,
        target_size=(1024, 768),
        max_bytes=900_000,
        quality_steps=(78, 70, 62),
    )

    assert str(saved["url"]).startswith("/media/posts/post-test/image-")
    assert int(saved["byte_size"]) <= 900_000
    assert int(saved["width"]) <= 1024
    assert int(saved["height"]) <= 768


def _png_bytes(*, size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", size, color)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def datetime_utc() -> datetime:
    return datetime(2026, 6, 15, tzinfo=UTC)


def _character_stub() -> SimpleNamespace:
    return SimpleNamespace(
        name="test character",
        one_liner="a quiet test character",
        personality="calm",
        speech_style="plain",
        worldview="curious",
        topic_preferences="daily life",
        safety_rules="",
    )
