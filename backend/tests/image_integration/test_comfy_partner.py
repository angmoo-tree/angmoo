"""Separate Partner credentials and official headless wire contract, offline."""
import asyncio
from copy import deepcopy
import json

import httpx
import pytest
from sqlalchemy import select

from app.domains.identity.contracts import CredentialPurpose
from app.domains.identity.models import User
from app.domains.identity.models_media import MediaCredential
from app.domains.identity.service import media_credentials
from app.domains.media.generation_contracts import ComfyOptions, GenerationRequest, EffectiveReference, ImagePreparationError
from app.domains.media.setting_schemas import GenerationSettingsWrite
from app.integrations.comfy_images import ComfyImageClient
from app.runtime.media.composition import MediaRuntime
from app.domains.social.models.image_intents import ImageIntent
from types import SimpleNamespace
from image_integration.test_generation_lifecycle import _session_factory, OWNER, CHARACTER, admit
from image_integration.test_providers import Http, png


INFO = {
    "PartnerImage": {"api_node": True, "input": {"required": {"prompt": ["STRING", {}]}}, "output": ["IMAGE"]},
    "SaveImage": {"output_node": True, "input": {"required": {"images": ["IMAGE", {}]}}, "output": []},
}
WORKFLOW = {"prompt": {"1": {"class_type": "PartnerImage", "inputs": {"prompt": "scene"}},
    "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}}},
    "bindings": {"positive": {"node_id": "1", "input_name": "prompt"}}, "output_node": "2"}


def transport(info=INFO):
    def respond(method, url, kwargs):
        if url.endswith("/object_info"):
            return httpx.Response(200, json=info)
        if url.endswith("/prompt"):
            return httpx.Response(200, json={"prompt_id": "partner-receipt"})
        if "/history/" in url:
            return httpx.Response(200, json={"partner-receipt": {"outputs": {"2": {"images": [
                {"filename": "result.png", "subfolder": "", "type": "output"}]}}}})
        return httpx.Response(200, content=png(), headers={"content-type": "image/png"})
    return Http(respond)


@pytest.mark.parametrize("enabled", [False, True])
def test_partner_detection_requires_matching_auth_mode(enabled):
    options = ComfyOptions(partner_auth=enabled, workflow=WORKFLOW)
    call = ComfyImageClient(options.base_url, transport()).validate(options)
    if enabled:
        assert asyncio.run(call) == INFO
    else:
        with pytest.raises(ImagePreparationError, match="comfy_partner_auth_required"):
            asyncio.run(call)


def test_partner_body_uses_account_key_and_headers_use_server_key_once():
    http = transport()
    options = ComfyOptions(partner_auth=True, workflow=WORKFLOW)
    request = GenerationRequest("comfyui", "workflow", "new scene", None, options.model_dump(), EffectiveReference(False))
    receipts = []
    async def receipt(value):
        receipts.append(value)
    client = ComfyImageClient(options.base_url, http)
    asyncio.run(client.generate(request, "synthetic-server-key", None, partner_key="synthetic-account-key", on_receipt=receipt))
    posts = [entry for entry in http.calls if entry[1].endswith("/prompt")]
    assert len(posts) == 1 and receipts == ["partner-receipt"]
    assert posts[0][2]["key"] == "synthetic-server-key"
    assert posts[0][2]["json"]["extra_data"] == {"api_key_comfy_org": "synthetic-account-key"}
    assert "synthetic-account-key" not in json.dumps(posts[0][2]["json"]["prompt"])
    http.calls.clear()
    asyncio.run(client.generate(request, "synthetic-server-key", None, partner_key="synthetic-account-key",
        on_receipt=receipt, receipt="partner-receipt"))
    assert all(method == "GET" and "extra_data" not in kwargs for method, _, kwargs in http.calls)


def test_missing_account_key_fails_before_any_network_or_submission():
    options = ComfyOptions(partner_auth=True, workflow=WORKFLOW)
    request = GenerationRequest("comfyui", "workflow", "scene", None, options.model_dump(), EffectiveReference(False))
    http = transport()
    with pytest.raises(ImagePreparationError, match="comfy_partner_key_required"):
        asyncio.run(ComfyImageClient(options.base_url, http).generate(request, "server", None, on_receipt=None))
    assert http.calls == []


def test_nonpartner_does_not_receive_account_key():
    info = deepcopy(INFO)
    info["PartnerImage"]["api_node"] = False
    options = ComfyOptions(workflow=WORKFLOW)
    request = GenerationRequest("comfyui", "workflow", "scene", None, options.model_dump(), EffectiveReference(False))
    http = transport(info)
    async def receipt(_):
        pass
    asyncio.run(ComfyImageClient(options.base_url, http).generate(request, None, None,
        partner_key="must-not-send", on_receipt=receipt))
    assert all("must-not-send" not in json.dumps(kwargs) for _, _, kwargs in http.calls)


def test_partner_credential_envelope_snapshot_reload_delete_and_revision(tmp_path):
    sessions = _session_factory(tmp_path)
    media = MediaRuntime(sessions, SimpleNamespace(media_root_path=tmp_path / "media"))
    options = ComfyOptions(partner_auth=True, workflow=WORKFLOW).model_dump(exclude_none=True)
    with sessions() as db:
        user = db.get(User, OWNER)
        data = GenerationSettingsWrite(expected_revision=0, provider="comfyui", model="workflow", auto_enabled=True,
            daily_limit=2, installation_daily_limit=2, options=options,
            api_key="synthetic-server-key", partner_api_key="synthetic-account-key")
        saved = media.write_generation(db, user, CHARACTER, data, validated_connection={"ready": True, "reference_supported": False})
        db.commit()
        assert saved["has_api_key"] and saved["has_partner_api_key"]
        assert "synthetic" not in json.dumps(media.read_generation(db, user, CHARACTER))
        rows = db.scalars(select(MediaCredential)).all()
        assert len(rows) == 2 and len({row.purpose for row in rows}) == 2
        assert all(row.encrypted_secret not in {"synthetic-server-key", "synthetic-account-key"} for row in rows)
    identity = admit(sessions, media)
    from app.domains.social.models.posts import PostImageGenerationJob
    with sessions() as db:
        job = db.get(PostImageGenerationJob, identity)
        execution = media.prepare(db, job, db.get(ImageIntent, job.intent_id))
        assert execution.key == "synthetic-server-key" and execution.partner_key == "synthetic-account-key"
        assert "synthetic" not in repr(execution)
        media_credentials.save_credential(db, owner_id=OWNER, character_id=CHARACTER, provider="comfyui",
            purpose=CredentialPurpose.COMFY_PARTNER_IMAGE, secret="replacement")
        db.commit()
        with pytest.raises(Exception, match="generation_source_or_key_changed"):
            media.prepare(db, job, db.get(ImageIntent, job.intent_id))
        previous = media.read_generation(db, db.get(User, OWNER), CHARACTER)
        saved = media.write_generation(db, db.get(User, OWNER), CHARACTER,
            data.model_copy(update={"expected_revision": previous["revision"], "auto_enabled": False,
                "api_key": None, "partner_api_key": None, "clear_partner_api_key": True}))
        db.commit()
        assert saved["has_api_key"] and not saved["has_partner_api_key"]


@pytest.mark.parametrize("clear_field", ["clear_partner_api_key", "clear_api_key"])
def test_delete_credential_preserves_validated_reference_preference_while_off(tmp_path, clear_field):
    sessions = _session_factory(tmp_path)
    media = MediaRuntime(sessions, SimpleNamespace(media_root_path=tmp_path / "media"))
    options = ComfyOptions(partner_auth=True, workflow=WORKFLOW).model_dump(exclude_none=True)
    with sessions() as db:
        user = db.get(User, OWNER)
        initial = GenerationSettingsWrite(expected_revision=0, provider="comfyui", model="workflow",
            auto_enabled=True, daily_limit=2, installation_daily_limit=2, reference_enabled=True,
            options=options, api_key="synthetic-server", partner_api_key="synthetic-partner")
        saved = media.write_generation(db, user, CHARACTER, initial,
            validated_connection={"ready": True, "reference_supported": True})
        db.commit()
        deleting = initial.model_copy(update={"expected_revision": saved["revision"], "auto_enabled": False,
            "api_key": None, "partner_api_key": None, clear_field: True})
        saved = media.write_generation(db, user, CHARACTER, deleting)
        db.commit()
        reloaded = media.read_generation(db, user, CHARACTER)
        assert not reloaded["auto_enabled"]
        assert reloaded["active_profile"]["reference_enabled"] is True
        assert reloaded["active_profile"]["options"] == options
        assert reloaded["active_profile"]["connection"] is None
        assert not reloaded["has_partner_api_key" if clear_field == "clear_partner_api_key" else "has_api_key"]
        with pytest.raises(ImagePreparationError):
            media.write_generation(db, user, CHARACTER, deleting.model_copy(update={
                "expected_revision": saved["revision"], "auto_enabled": True, clear_field: False}))
