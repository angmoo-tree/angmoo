import asyncio
import base64
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

import httpx
import pytest
from PIL import Image

from app.domains.media.generation_contracts import GenerationRequest, EffectiveReference, NovelOptions, ComfyOptions, ComfyWorkflow, ImagePreparationError, ImageSubmissionError, MODEL_CATALOG
from app.integrations.image_api import ImageApiClient, ImageHttp, endpoint_parameters, validate_api_options
from app.integrations.novelai_images import NovelImageClient, precise_pixels, validate_t5_prompt
from app.integrations.comfy_images import ComfyImageClient, inject_workflow, validate_workflow
from app.integrations import image_api


def png():
    output = BytesIO()
    Image.new("RGB", (18, 24), "blue").save(output, "PNG")
    return output.getvalue()


class Http:
    def __init__(self, responder):
        self.calls, self.responder = [], responder
    async def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responder(method, url, kwargs)


CATALOG = json.loads(Path(image_api.__file__).with_name("image_catalog.json").read_text("utf-8"))["models"]
API_MODELS = [(p, m, ref) for p, m, ref in MODEL_CATALOG.values() if p in {"nanogpt", "openrouter"}]


@pytest.mark.parametrize("provider,model,support", API_MODELS)
@pytest.mark.parametrize("reference_on", [False, True])
def test_six_api_models_serialize_their_actual_profile(provider, model, support, reference_on):
    endpoint = CATALOG[f"{provider}:{model}"]["payload"]["endpoints"][0]
    http = Http(lambda *_: httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(png()).decode(), "media_type": "image/png"}]}))
    request = GenerationRequest(provider, model, "ink, short hair, reading at a desk", None, {}, EffectiveReference(reference_on), endpoint)
    client = ImageApiClient(provider, http)
    if reference_on and not support:
        with pytest.raises(ImagePreparationError, match="reference_not_supported"):
            asyncio.run(client.generate(request, "fake", png()))
        assert http.calls == []
        return
    result = asyncio.run(client.generate(request, "fake", png() if reference_on else None))
    assert result.content == png() and result.usage is None
    method, url, kwargs = http.calls[0]
    assert method == "POST" and url.endswith("/api/v1/images")
    body = kwargs["json"]
    assert body["model"] == model and body["n"] == 1 and "negative_prompt" not in body
    assert ("input_references" in body) == reference_on
    if reference_on:
        assert len(body["input_references"]) == 1
    if provider == "openrouter":
        assert body["provider"] == {"only": [endpoint["provider_tag"]], "allow_fallbacks": False}
    else:
        assert "provider" not in body


@pytest.mark.parametrize("provider,model,support", API_MODELS)
def test_profiles_reject_foreign_options_and_empty_routes(provider, model, support):
    endpoint = CATALOG[f"{provider}:{model}"]["payload"]["endpoints"][0]
    with pytest.raises(ImagePreparationError, match="option_unsupported"):
        validate_api_options(provider, endpoint, {"steps": 28})
    http = Http(lambda *_: httpx.Response(200, json={"id": model, "endpoints": []}))
    with pytest.raises(ImagePreparationError, match="model_endpoint_unavailable"):
        asyncio.run(ImageApiClient(provider, http).discover(model))
    assert len(http.calls) == 1 and http.calls[0][0] == "GET"


@pytest.mark.parametrize("tier,active,expires,valid", [(3, True, 9999999999, True), (1, True, 9999999999, False), (2, True, 9999999999, False), (3, False, 9999999999, False), (3, True, 1, False)])
def test_novel_opus_authorization_is_checked_without_paid_fallback(tier, active, expires, valid, monkeypatch):
    # Isolate serializer/account rules behind a synthetic verified capability.
    # A separate regression asserts production's unverified gate blocks all I/O.
    monkeypatch.setattr(NovelImageClient, "prompt_validation", staticmethod(lambda: {"exact_verified": True}))
    http = Http(lambda method, *_: httpx.Response(200, json={"tier": tier, "active": active, "expiresAt": expires}) if method == "GET" else httpx.Response(200, json={"images": [{"image": base64.b64encode(png()).decode()}]}))
    request = GenerationRequest("novelai", "nai-diffusion-4-5-full", "blue sky", "blur", NovelOptions().model_dump(), EffectiveReference(False))
    if not valid:
        with pytest.raises(ImagePreparationError, match="opus_benefit_unverified"):
            asyncio.run(NovelImageClient(http).generate(request, "fake", None))
        assert all(call[0] == "GET" for call in http.calls)
    else:
        result = asyncio.run(NovelImageClient(http).generate(request, "fake", None))
        body = http.calls[-1][2]["json"]
        assert result.content == png() and body["input"] == "blue sky"
        params = body["parameters"]
        assert params["n_samples"] == 1 and params["steps"] <= 28
        assert not any("reference" in key or key == "image" for key in params)
        assert params["negative_prompt"] == "blur"


def test_novel_paid_reference_and_zip_pixels_do_not_extract_paths(monkeypatch):
    monkeypatch.setattr(NovelImageClient, "prompt_validation", staticmethod(lambda: {"exact_verified": True}))
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("../../not-a-local-file.png", png())
    http = Http(lambda *_: httpx.Response(200, content=output.getvalue(), headers={"content-type": "application/zip"}))
    options = NovelOptions(mode="allow_anlas", reference_type="character", reference_strength=.7, reference_fidelity=.6)
    request = GenerationRequest("novelai", "nai-diffusion-4-5-full", "blue sky", None, options.model_dump(), EffectiveReference(True))
    result = asyncio.run(NovelImageClient(http).generate(request, "fake", png()))
    params = http.calls[0][2]["json"]["parameters"]
    assert result.content == png() and len(params["director_reference_images"]) == 1
    assert params["director_reference_strength_values"] == [.7]
    with Image.open(BytesIO(base64.b64decode(params["director_reference_images"][0]))) as image:
        assert image.size == (1024, 1536)
    with pytest.raises(ImagePreparationError, match="unsupported_text"):
        validate_t5_prompt("한국어 캐릭터")
    with pytest.raises(ImagePreparationError, match="prompt_limit"):
        validate_t5_prompt("a long scene " * 600)


def samples():
    root = Path(__file__).parents[2] / "app/domains/media/samples"
    return {name: json.loads((root / f"comfy-{name}.json").read_text("utf-8")) for name in ("text", "reference")}


def object_info():
    # A recorded core-node contract, without a ComfyUI install or checkpoint weights.
    return {
        "CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["choose-installed-model.safetensors"]]}}, "output": ["MODEL", "CLIP", "VAE"]},
        "CLIPTextEncode": {"input": {"required": {"text": ["STRING"], "clip": ["CLIP"]}}, "output": ["CONDITIONING"]},
        "EmptyLatentImage": {"input": {"required": {"width": ["INT", {"min": 64, "max": 4096}], "height": ["INT", {"min": 64, "max": 4096}], "batch_size": ["INT", {"min": 1, "max": 1}]}}, "output": ["LATENT"]},
        "KSampler": {"input": {"required": {"model": ["MODEL"], "positive": ["CONDITIONING"], "negative": ["CONDITIONING"], "latent_image": ["LATENT"], "seed": ["INT", {"min": 0, "max": 18446744073709551615}], "steps": ["INT", {"min": 1, "max": 100}], "cfg": ["FLOAT", {"min": 0, "max": 100}], "sampler_name": [["euler"]], "scheduler": [["normal"]], "denoise": ["FLOAT", {"min": 0, "max": 1}]}}, "output": ["LATENT"]},
        "VAEDecode": {"input": {"required": {"samples": ["LATENT"], "vae": ["VAE"]}}, "output": ["IMAGE"]},
        "VAEEncode": {"input": {"required": {"pixels": ["IMAGE"], "vae": ["VAE"]}}, "output": ["LATENT"]},
        "LoadImage": {"input": {"required": {"image": [["uploaded.png"]]}}, "output": ["IMAGE", "MASK"]},
        "ImageScale": {"input": {"required": {"image": ["IMAGE"], "width": ["INT"], "height": ["INT"], "upscale_method": [["lanczos"]], "crop": [["disabled"]]}}, "output": ["IMAGE"]},
        "SaveImage": {"input": {"required": {"images": ["IMAGE"], "filename_prefix": ["STRING"]}}, "output": [], "output_node": True},
    }


@pytest.mark.parametrize("kind", ["text", "reference"])
def test_comfy_samples_use_typed_bindings_without_mutating_json(kind):
    sample = samples()[kind]
    workflow = ComfyWorkflow.model_validate(sample["workflow"])
    before = deepcopy(workflow.prompt)
    values = {**sample["values"], "positive": "scene", "negative": "blur", "seed": -1}
    if kind == "reference":
        values["reference"] = "uploaded.png"
    validate_workflow(workflow, object_info())
    # Execution resolves the -1 sentinel before injection.
    values["seed"] = 7
    result = inject_workflow(workflow, object_info(), values)
    assert workflow.prompt == before
    for field, value in values.items():
        binding = workflow.bindings[field]
        assert result[binding.node_id]["inputs"][binding.input_name] == value
    with pytest.raises(ImagePreparationError):
        inject_workflow(workflow, object_info(), {**values, "steps": "20"})
    with pytest.raises(ImagePreparationError, match="link_invalid"):
        broken = workflow.model_copy(deep=True)
        broken.prompt["7"]["inputs"]["images"] = ["1", 0]
        validate_workflow(broken, object_info())


def test_comfy_receipt_recovery_does_not_resubmit_or_interrupt():
    sample = samples()["reference"]
    options = ComfyOptions(base_url="http://127.0.0.1:8188", workflow=sample["workflow"], text_workflow=samples()["text"]["workflow"], values=sample["values"])
    def respond(method, url, args):
        if url.endswith("/object_info"):
            return httpx.Response(200, json=object_info())
        if url.endswith("/upload/image"):
            return httpx.Response(200, json={"name": "uploaded.png", "subfolder": "", "type": "input"})
        if url.endswith("/prompt"):
            return httpx.Response(200, json={"prompt_id": "receipt-1", "node_errors": {}})
        if "/history/" in url:
            return httpx.Response(200, json={"receipt-1": {"outputs": {"7": {"images": [{"filename": "output.png", "subfolder": "", "type": "output"}]}}}})
        return httpx.Response(200, content=png(), headers={"content-type": "image/png"})
    http = Http(respond)
    client = ComfyImageClient(options.base_url, http)
    request = GenerationRequest("comfyui", "workflow", "scene", "blur", options.model_dump(), EffectiveReference(True))
    receipts = []
    async def received(value):
        receipts.append(value)
    first = asyncio.run(client.generate(request, None, png(), on_receipt=received))
    second = asyncio.run(client.generate(request, None, png(), on_receipt=received, receipt="receipt-1"))
    assert first.content == second.content == png() and receipts == ["receipt-1"]
    assert sum(url.endswith("/prompt") for _, url, _ in http.calls) == 1
    assert not any("/interrupt" in url for _, url, _ in http.calls)
    assert sum(url.endswith("/upload/image") for _, url, _ in http.calls) == 1


def test_http_transport_errors_are_redacted_and_not_retried():
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("secret-value remote message", request=request)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ImageSubmissionError) as captured:
                await ImageHttp(client).request("POST", "https://api.nano-gpt.com/api/v1/images", key="secret-value", json={"prompt": "scene"})
            assert captured.value.outcome_unknown and "secret-value" not in str(captured.value)
    asyncio.run(run())
    assert len(calls) == 1
