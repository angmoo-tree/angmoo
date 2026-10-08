"""Independent synthetic contracts: no installed data, nodes, models or AI calls."""
import asyncio
import base64
from copy import deepcopy
from dataclasses import asdict, replace
from io import BytesIO
import json

import httpx
import pytest
from PIL import Image, PngImagePlugin
from pydantic import ValidationError
from sqlalchemy import select

from app.domains.media.service.comfy_workflows import (TOKENS, MAX_GRAPH_BYTES, analyze_source,
    bounded_json, freeze_comfy_request, prepare_values, render_workflow, restore_generation_request, strict_json)
from app.domains.media.generation_contracts import (ComfyOptions, EffectiveReference, GenerationRequest,
    ImagePreparationError, ImageSubmissionError)
from app.integrations.comfy_images import ComfyImageClient, javascript_keys, reference_base64, select_image, validate_base_url
from app.integrations.image_api import ImageHttp
from app.domains.social.models.image_intents import ImageIntent
from app.domains.social.models.posts import PostImageGenerationJob
from app.domains.identity.models import User
from app.domains.media.setting_schemas import GenerationSettingsWrite
from image_integration.test_generation_lifecycle import configured, admit, OWNER, CHARACTER
from image_integration.test_providers import Http, png, samples


def graph(inputs=None):
    return {"9": {"class_type": "UninstalledCustomNode", "inputs": inputs or {"anything": "%prompt%"}}}


def options(prompt=None, **changes):
    return ComfyOptions.model_validate({"options_schema_version": 2, "workflow": {"input_mode": "placeholders",
        "prompt": graph() if prompt is None else prompt}, **changes})


def request(config=None, reference=None):
    return GenerationRequest("comfyui", "workflow", "actual caller scene", "actual negative", (config or options()).model_dump(), reference or EffectiveReference(False))


def transport(history=None, submitted=None, view=None, candidate=None):
    def respond(method, url, kwargs):
        if url.endswith("/system_stats"):
            return httpx.Response(200, json={"system": {"os": "mock"}})
        if url.endswith("/object_info"):
            return candidate or httpx.Response(503)
        if url.endswith("/prompt"):
            return submitted or httpx.Response(200, json={"prompt_id": "test-receipt"})
        if "/history/" in url:
            return httpx.Response(200, json={"test-receipt": history or {"status": {"completed": True, "status_str": "success"},
                "outputs": {"9": {"images": [{"filename": "first.png", "subfolder": "", "type": "output"}]}}}})
        if url.endswith("/view"):
            return view or httpx.Response(200, content=png(), headers={"content-type": "image/png"})
        raise AssertionError("unexpected network route")
    return Http(respond)


async def received(_):
    pass


def test_legacy_round_trip_and_explicit_discriminants():
    old = ComfyOptions(workflow=samples()["text"]["workflow"], values=samples()["text"]["values"])
    encoded = old.model_dump(exclude_none=True)
    assert "options_schema_version" not in encoded and "clip_skip_value_mode" not in encoded
    assert ComfyOptions.model_validate(encoded).model_dump(exclude_none=True) == encoded
    for change in ({"options_schema_version": 3}, {"workflow": {"input_mode": "other", "prompt": graph()}},
        {"workflow": {"input_mode": "placeholders", "prompt": graph(), "output": {"mode": "other"}}},
        {"options_schema_version": 2, "workflow": old.workflow.model_dump()}):
        with pytest.raises(ValidationError):
            ComfyOptions.model_validate({**options().model_dump(), **change})


@pytest.mark.parametrize("raw,code", [('{"9":1,"9":2}', "duplicate"), ('{"9":{"inputs":{"x":1,"x":2}}}', "duplicate"),
    ('{"9": NaN}', "invalid"), ('{"9":Infinity}', "invalid"), ('{"a":1e400}', "invalid")])
def test_raw_json_preserves_strict_errors(raw, code):
    with pytest.raises(ImagePreparationError, match=code):
        strict_json(raw)


def test_tree_limits_and_editor_format():
    with pytest.raises(ImagePreparationError, match="size"):
        strict_json('"' + "x" * MAX_GRAPH_BYTES + '"')
    for value in ({"nodes": []}, {"a": {"class_type": "Node", "inputs": []}}, {}):
        with pytest.raises(ImagePreparationError):
            analyze_source(json.dumps(value))
    with pytest.raises(ImagePreparationError, match="complexity"):
        strict_json("[" * 65 + "0" + "]" * 65)
    with pytest.raises(ImagePreparationError, match="complexity"):
        strict_json(json.dumps([0] * 100_001))


def test_all_14_exact_tokens_nested_literal_keys_links_and_metadata():
    inputs = {"data": {"a.b": [{"a/b": list(TOKENS)}, "%prompt% constant", "%unknown%", ["absent", 999]],
        "integer": ["%width%", "%width%"]}, "file": "prefix_%seed%.png"}
    source = graph(inputs)
    source["9"]["_meta"] = {"title": "%prompt%"}
    original = deepcopy(source)
    analysis = analyze_source(json.dumps(source))
    assert set(analysis["used_roles"]) == set(TOKENS.values())
    assert len(analysis["positions"]) == 16
    config = options(source)
    supplied = {role: 7 if role in {"width", "height", "steps", "seed", "clip_skip"} else .5 if role in {"cfg", "denoise"} else "value-" + role for role in TOKENS.values()}
    result = render_workflow(config.workflow, supplied)
    assert source == original
    for location in analysis["positions"]:
        value = result[location["node_id"]]["inputs"]
        for item in [location["input_name"], *location["path"]]: value = value[item]
        assert value == supplied[location["role"]]
    assert result["9"]["inputs"]["data"]["a.b"][1:] == inputs["data"]["a.b"][1:]
    assert result["9"]["inputs"]["file"] == "prefix_%seed%.png" and result["9"]["_meta"] == original["9"]["_meta"]


@pytest.mark.parametrize("role,bad", [("width", True), ("height", 4.5), ("steps", "20"), ("seed", False), ("clip_skip", 1.5), ("cfg", "5"), ("denoise", float("inf"))])
def test_required_values_are_typed_without_coercion(role, bad):
    token = next(token for token, used in TOKENS.items() if used == role)
    with pytest.raises((ValidationError, ImagePreparationError)):
        prepare_values(options(graph({"input": token}), values={role: bad}), options(graph({"input": token})).workflow)


def test_fixed_prompt_unused_roles_and_missing_values():
    config = options(graph({"text": "fixed prompt", "any": "%extension_only%"}), values={"height": "unused invalid type"})
    assert prepare_values(config, config.workflow) == {}
    assert render_workflow(config.workflow, {}) == config.workflow.prompt
    needed = options(graph({"width": "%width%"}))
    with pytest.raises(ImagePreparationError, match="comfy_value_required"):
        prepare_values(needed, needed.workflow)


def test_seed_clip_snapshot_round_trip_is_single_and_secret_free(monkeypatch):
    calls = []
    monkeypatch.setattr("app.domains.media.service.comfy_workflows.secrets.randbits", lambda bits: calls.append(bits) or 12345)
    config = options(graph({"seed": "%seed%", "twice": ["%seed%", "%clip_skip%"], "text": "%prompt%"}), values={"seed": -1, "clip_skip": 2})
    prepared = freeze_comfy_request(request(config))
    assert prepared.comfy_execution.seed == 12345 and prepared.comfy_execution.clip_skip_actual == -2
    assert prepared.comfy_execution.clip_skip_display == 2
    restored = restore_generation_request(json.loads(json.dumps(asdict(prepared))))
    assert freeze_comfy_request(restored) == prepared and calls == [32]
    rendered = render_workflow(config.workflow, prepared.comfy_execution.prepared_values)
    assert rendered["9"]["inputs"]["twice"] == [12345, -2]
    assert "base64" not in json.dumps(asdict(prepared)) and "reference" not in prepared.comfy_execution.prepared_values
    direct = config.model_copy(update={"clip_skip_value_mode": "node_value", "values": {"seed": 77, "clip_skip": -2}})
    assert freeze_comfy_request(request(direct)).comfy_execution.clip_skip_actual == -2
    assert calls == [32]


def test_reference_metadata_stripped_encoded_once_arbitrary_node(monkeypatch):
    metadata = PngImagePlugin.PngInfo(); metadata.add_text("chara", "private card")
    output = BytesIO(); Image.new("RGB", (24, 18), "green").save(output, "PNG", pnginfo=metadata)
    encoded = reference_base64(output.getvalue())
    with Image.open(BytesIO(base64.b64decode(encoded))) as image:
        assert image.size == (24, 18) and not image.info
    import app.integrations.comfy_images as module
    original = module.reference_base64; count = []
    monkeypatch.setattr(module, "reference_base64", lambda content: count.append(1) or original(content))
    config = options(graph({"arbitrary": ["%char_avatar%", {"again": "%char_avatar%"}]}))
    http = transport(); asyncio.run(ComfyImageClient(config.base_url, http).generate(request(config), None, output.getvalue(), on_receipt=received))
    body = json.loads(next(args["content"] for _, url, args in http.calls if url.endswith("/prompt")))
    actual = body["prompt"]["9"]["inputs"]["arbitrary"]
    assert actual == [encoded, {"again": encoded}] and count == [1]
    assert not actual[0].startswith("data:") and not any("/upload/" in url for _, url, _ in http.calls)


def test_fallback_is_chosen_before_submit_and_only_selected_values_needed():
    config = options(graph({"avatar": "%char_avatar%", "missing": "%width%"}), text_workflow={"input_mode": "placeholders", "prompt": graph({"text": "%prompt%"})})
    frozen = freeze_comfy_request(request(config))
    assert frozen.comfy_execution.selected_path == "text_workflow"
    http = transport()
    checked = asyncio.run(ComfyImageClient(config.base_url, http).validate(config, has_reference=False))
    assert checked["ready"] and checked["candidate_lookup"]["state"] == "unavailable"
    assert checked["input_readiness"]["path"] == "text_workflow"
    assert all(method == "GET" for method, _, _ in http.calls)
    asyncio.run(ComfyImageClient(config.base_url, http).generate(frozen, None, None, on_receipt=received))
    assert sum(url.endswith("/prompt") for _, url, _ in http.calls) == 1


@pytest.mark.parametrize("base", ["http://comfyui:8188", "http://host.docker.internal:8188/base", "https://example.test/comfy", "http://[::1]:8188", "http://localhost:8188"])
def test_url_keeps_host_and_base_path(base):
    assert validate_base_url(base + "/") == base
    http = transport(); asyncio.run(ComfyImageClient(base, http).validate(options(), has_reference=False))
    assert http.calls[0][1] == base + "/system_stats"


@pytest.mark.parametrize("base", ["file:///tmp", "http://a@b", "http://:secret@host", "http://host?key=x", "http://host#frag", "http://host:99999", "http://host/a b"])
def test_url_rejects_non_base_components(base):
    with pytest.raises(ImagePreparationError, match="url_invalid"): validate_base_url(base)


def test_javascript_key_order_first_preview_batch_and_no_replacement():
    keys = ["01", "9", "-1", "4294967295", "2", "0", "١", "4294967294", "alpha"]
    assert javascript_keys(dict.fromkeys(keys)) == ["0", "2", "9", "4294967294", "01", "-1", "4294967295", "١", "alpha"]
    outputs = {"12": {"images": [{"filename": "later"}]}, "2": {"images": [{"filename": "preview"}, {"filename": "batch2"}]}}
    assert select_image(outputs, {"mode": "auto_first_image"})["filename"] == "preview"
    assert select_image(outputs, {"mode": "explicit_node", "node_id": "12"})["filename"] == "later"
    with pytest.raises(ImageSubmissionError): select_image(outputs, {"mode": "legacy_single", "node_id": "2"})
    outputs["2"]["images"][0] = None
    assert select_image(outputs, {"mode": "auto_first_image"}) is None


@pytest.mark.parametrize("history,code", [({"status": {"completed": True}, "outputs": {}}, "no_image_output"),
    ({"status": {"completed": True, "status_str": "error", "messages": [["execution_error", {"exception_message": "failure"}]]}, "outputs": {"9": {"images": [{"filename": "ignored"}]}}}, "execution_failed"),
    ({"status": {"completed": True}, "outputs": {"9": {"images": [None]}, "10": {"images": [{"filename": "second.png", "type": "output"}]}}}, "output_shape_invalid")])
def test_completed_failures_are_terminal_even_if_other_images_exist(history, code):
    http = transport(history=history)
    with pytest.raises(ImageSubmissionError, match=code) as caught:
        asyncio.run(ComfyImageClient(options().base_url, http).generate(request(), None, None, on_receipt=received))
    assert caught.value.receipt == "test-receipt" and not caught.value.outcome_unknown
    assert not any(url.endswith("/view") for _, url, _ in http.calls)


def test_pending_timeout_and_receipt_recovery_never_resubmit():
    http = transport(history={"status": {"completed": False}, "outputs": {}})
    with pytest.raises(ImageSubmissionError, match="timeout") as caught:
        asyncio.run(ComfyImageClient(options().base_url, http).generate(request(), None, None, on_receipt=received, receipt="test-receipt", timeout=.01))
    assert caught.value.outcome_unknown and all(method == "GET" for method, _, _ in http.calls)


def test_submission_diagnostics_redact_selected_fields_and_receipt_warning_survives():
    payload = {"prompt_id": "test-receipt", "node_errors": {"9": {"class_type": "Custom", "errors": [
        {"type": "invalid", "message": "actual caller scene server-secret", "inputs": {"key": "server-secret"}, "traceback": ["forbidden"]}]}}}
    http = transport(submitted=httpx.Response(200, json=payload)); warnings = []
    async def warn(value): warnings.append(value)
    result = asyncio.run(ComfyImageClient(options().base_url, http).generate(request(), "server-secret", None, on_receipt=received, on_diagnostic=warn))
    assert result.diagnostic["kind"] == "warning" and warnings == [result.diagnostic]
    encoded = json.dumps(result.diagnostic)
    assert "actual caller scene" not in encoded and "server-secret" not in encoded and "forbidden" not in encoded and "inputs" not in encoded
    assert result.receipt == "test-receipt"


@pytest.mark.parametrize("status,unknown", [(400, False), (500, True)])
def test_rejected_submission_classification(status, unknown):
    payload = {"error": {"type": "invalid_prompt", "message": "custom node rejected"}}
    http = transport(submitted=httpx.Response(status, json=payload))
    with pytest.raises(ImageSubmissionError, match="prompt_rejected") as caught:
        asyncio.run(ComfyImageClient(options().base_url, http).generate(request(), None, None, on_receipt=received))
    assert caught.value.outcome_unknown is unknown and caught.value.diagnostic["messages"][0]["type"] == "invalid_prompt"
    assert len(http.calls) == 1


def test_bounded_error_body_opt_in_does_not_change_other_provider_http_behavior():
    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(400, content=b"x" * 100_000))) as client:
            http = ImageHttp(client)
            response = await http.request("POST", "http://synthetic/prompt", error_body_limit=32 * 1024)
            assert len(response.content) == 32 * 1024 and response.extensions["angmoo_body_truncated"]
            with pytest.raises(ImageSubmissionError, match="provider_http_400"):
                await http.request("POST", "http://synthetic/other")
    asyncio.run(check())
    with pytest.raises(ImagePreparationError, match="too_large"): bounded_json({"x": "a" * 4096}, limit=1024)


def test_character_runtime_admission_snapshot_and_worker_warning_persist(tmp_path):
    sessions, media, fake = configured(tmp_path, "comfyui", "workflow")
    config = options(graph({"text": "%prompt%", "negative": "%negative_prompt%", "seed": "%seed%", "clip": "%clip_skip%"}), values={"seed": -1, "clip_skip": 1})
    with sessions() as db:
        saved = media.read_generation(db, db.get(User, OWNER), CHARACTER)
        media.write_generation(db, db.get(User, OWNER), CHARACTER, GenerationSettingsWrite(expected_revision=saved["revision"], provider="comfyui", model="workflow", auto_enabled=True,
            daily_limit=4, style="ink", appearance="short hair", negative="blur", options=config.model_dump()), validated_connection={"ready": True, "reference_supported": False})
        db.commit()
    job_id = admit(sessions, media)
    with sessions() as db:
        row = db.get(PostImageGenerationJob, job_id); captured = json.loads(db.get(ImageIntent, row.intent_id).request_json)
        assert captured["comfy_execution"]["prepared_values"]["positive"] == "ink, short hair, reading at a desk"
        assert captured["comfy_execution"]["clip_skip_actual"] == -1
        original = restore_generation_request(captured)
    http = transport(submitted=httpx.Response(200, json={"prompt_id": "test-receipt", "node_errors": {"9": {"errors": [{"type": "warning", "message": "safe warning"}]}}}))
    media.clients["comfyui"] = ComfyImageClient(config.base_url, http)
    asyncio.run(media.worker.process(job_id))
    with sessions() as db:
        view = media.worker.view_for_post(db, OWNER, db.get(PostImageGenerationJob, job_id).post_id)
        assert view["status"] == "succeeded" and view["provider_diagnostic"]["kind"] == "warning"
        assert restore_generation_request(json.loads(db.get(ImageIntent, db.get(PostImageGenerationJob, job_id).intent_id).request_json)) == original
    assert sum(url.endswith("/prompt") for _, url, _ in http.calls) == 1
