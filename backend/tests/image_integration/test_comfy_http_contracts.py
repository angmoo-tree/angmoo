"""Raw decoding and authorized projections without an app runtime or AI client."""
import json
from dataclasses import asdict
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.domains.identity.service.http_auth import get_current_user
from app.domains.media.router import router, require_local_frontend_request
from app.domains.media.service.http_workflows import require_comfy_raw_json
from app.domains.media.schemas import diagnostic_projection
from app.domains.media.service.comfy_workflows import freeze_comfy_request, restore_generation_request
from app.domains.media.generation_contracts import ImagePreparationError
from image_integration.test_comfy_placeholders import graph, options, request


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="synthetic-owner")
    app.dependency_overrides[require_local_frontend_request] = lambda: None
    @app.post("/raw", dependencies=[Depends(require_comfy_raw_json)])
    def raw(body: dict):
        return body
    with TestClient(app) as client:
        yield client


def test_analysis_preserves_raw_semantics_and_requires_auth(client):
    source = json.dumps(graph({"text": "%prompt%", "custom": {"a/b": ["%seed%", ["9", 0]]}}))
    response = client.post("/media/comfy-workflows/analyze", json={"source_json": source})
    assert response.status_code == 200
    analyzed = response.json()
    assert analyzed["prompt"] == json.loads(source)
    assert next(position for position in analyzed["positions"] if position["role"] == "seed")["path"] == ["a/b", 0]
    def denied():
        raise HTTPException(401)
    client.app.dependency_overrides[get_current_user] = denied
    assert client.post("/media/comfy-workflows/analyze", json={"source_json": source}).status_code == 401


@pytest.mark.parametrize("source,code", [
    ('{"9":{"class_type":"Custom","inputs":{"x":1,"x":2}}}', "comfy_json_duplicate_key"),
    ('{"9":{"class_type":"Custom","inputs":{"x":NaN}}}', "comfy_json_invalid"),
    (json.dumps(graph({"x": 1})).replace('"x": 1', '"x": ' + '[' * 65 + '1' + ']' * 65), "comfy_json_complexity_exceeded"),
])
def test_raw_analysis_rejects_lossy_or_excessive_json(client, source, code):
    response = client.post("/media/comfy-workflows/analyze", json={"source_json": source})
    assert response.status_code == 422 and response.json()["detail"] == code


@pytest.mark.parametrize("raw", [
    '{"provider":"comfyui","options":{"values":{"seed":1,"seed":2}}}',
    '{"provider":"comfyui","provider":"novelai"}',
    '{"generation_settings":{"profiles":{"comfyui:workflow":{"options":{"a":1,"a":2}}}}}',
])
def test_write_guard_detects_duplicates_before_framework_collapses_keys(client, raw):
    response = client.post("/raw", content=raw, headers={"Content-Type": "application/json"})
    assert response.status_code == 422 and response.json()["detail"] == "comfy_json_duplicate_key"


def test_other_provider_decoder_contract_is_unchanged(client):
    response = client.post("/raw", content='{"provider":"novelai","a":1,"a":2}', headers={"Content-Type": "application/json"})
    assert response.status_code == 200 and response.json()["a"] == 2


def test_snapshot_rejects_mutated_modes_or_numeric_values():
    encoded = asdict(freeze_comfy_request(request(options(graph({"seed": "%seed%"}), values={"seed": 123}))))
    encoded["comfy_execution"]["seed"] = 124
    with pytest.raises(ImagePreparationError, match="snapshot_invalid"):
        restore_generation_request(encoded)
    encoded["comfy_execution"]["seed"] = 123
    encoded["comfy_execution"]["input_mode"] = "legacy_bindings"
    with pytest.raises(ImagePreparationError, match="snapshot_invalid"):
        restore_generation_request(encoded)


def test_untrusted_storage_diagnostics_cannot_leak_raw_fields():
    assert diagnostic_projection(None) is None
    assert diagnostic_projection("not-json") is None
    assert diagnostic_projection("[" * 1100 + "0" + "]" * 1100) is None
    assert diagnostic_projection("x" * 16385) is None
    assert diagnostic_projection({"kind": "error", "stage": "execution", "messages": [{"message": "safe", "inputs": "private"}]}) is None
    safe = {"kind": "warning", "stage": "submission", "messages": [{"message": "safe"}], "truncated": False}
    assert diagnostic_projection(json.dumps(safe)) == safe


@pytest.mark.parametrize("preference,saved_off,expected_path", [
    (None, False, "workflow"), (None, True, "text_workflow"), (False, False, "text_workflow"),
])
def test_character_reference_check_uses_requested_profile_and_actual_asset(tmp_path, monkeypatch, preference, saved_off, expected_path):
    import asyncio
    import httpx
    from app.domains.characters.models import AgentImageGenerationSetting
    from app.domains.identity.models import User
    from app.domains.media.setting_schemas import GenerationSettingsWrite
    from app.integrations.comfy_images import ComfyImageClient
    from app.runtime.media import composition
    from image_integration.test_generation_lifecycle import _session_factory, OWNER, CHARACTER
    from image_integration.test_providers import Http, png

    sessions = _session_factory(tmp_path)
    media = composition.MediaRuntime(sessions, SimpleNamespace(media_root_path=tmp_path / "media"))
    typed = options(graph({"avatar": "%char_avatar%"}))
    typed.text_workflow = options(graph({"text": "%prompt%"})).workflow
    http = Http(lambda method, url, kwargs: httpx.Response(200, json={"system": {}})
        if url.endswith("/system_stats") else httpx.Response(503, json={"unavailable": True}))
    monkeypatch.setattr(composition, "ComfyImageClient", lambda base_url: ComfyImageClient(base_url, http))
    with sessions() as db:
        user = db.get(User, OWNER)
        media.read_generation(db, user, CHARACTER)
        row = db.get(AgentImageGenerationSetting, CHARACTER)
        profiles = {"nanogpt:krea-v2/turbo:": {"active": True, "reference_initialized": True, "reference_enabled": False}}
        if saved_off:
            profiles["comfyui:workflow:"] = {"active": False, "reference_initialized": True, "reference_enabled": False}
        row.generation_profiles_json = json.dumps(profiles)
        asset = media.assets.upload(db, owner_id=OWNER, scope_kind="character", scope_id=CHARACTER,
            content_type="image/png", content=png())
        asset_id = asset.id
        db.commit()
        data = GenerationSettingsWrite(expected_revision=0, provider="comfyui", model="workflow", auto_enabled=False,
            reference_enabled=preference, reference_asset_id=asset_id, options=typed.model_dump(exclude_none=True))
        checked = asyncio.run(media.validate_connection(db, user, CHARACTER, data))
        assert checked["ready"] and checked["reference_supported"]
        assert checked["input_readiness"]["path"] == expected_path
        assert db.get(AgentImageGenerationSetting, CHARACTER).generation_profiles_json == json.dumps(profiles)
        assert all(method == "GET" for method, _, _ in http.calls)
        saved = media.write_generation(db, db.get(User, OWNER), CHARACTER, data, validated_connection=checked)
        assert saved["active_profile"]["reference_initialized"] is True
        assert saved["active_profile"]["reference_enabled"] is (expected_path == "workflow")
