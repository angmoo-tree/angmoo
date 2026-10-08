"""Isolated external JSON mock checks and optional no-model ComfyUI check.

External files remain outside the repository. This does not discover credentials,
start a server, install nodes/models, or submit external AI workflows.
"""
import argparse
import asyncio
from dataclasses import asdict
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
import httpx
from PIL import Image, PngImagePlugin
from app.domains.media.service.comfy_workflows import analyze_source, freeze_comfy_request, restore_generation_request
from app.domains.media.generation_contracts import ComfyOptions, GenerationRequest, EffectiveReference, ImageSubmissionError
from app.integrations.comfy_images import ComfyImageClient
from app.integrations.image_api import ImageHttp


def pixels():
    buffer = BytesIO(); meta = PngImagePlugin.PngInfo(); meta.add_text("chara", "synthetic-private-card")
    Image.new("RGBA", (128, 64), (30, 120, 70, 255)).save(buffer, "PNG", pnginfo=meta)
    return buffer.getvalue()


async def external_checks(args):
    official = json.loads((args.official / "official-sources.json").read_text("utf-8"))
    community = json.loads((args.community / "sources.json").read_text("utf-8"))["items"]
    reports = []
    for root, entries in ((args.official / "fixtures", official), (args.community, community)):
        for item in entries:
            source = (root / item["file"]).read_bytes()
            assert hashlib.sha256(source).hexdigest() == item["sha256"]
            analysis = analyze_source(source.decode("utf-8"))
            config = ComfyOptions(options_schema_version=2, workflow={"input_mode": "placeholders", "prompt": analysis["prompt"]},
                values={"model": "synthetic-model.safetensors", "vae": "synthetic-vae.safetensors", "width": 512, "height": 768,
                    "steps": 20, "cfg": 5.5, "sampler": "synthetic-sampler", "scheduler": "synthetic-scheduler", "seed": 123456,
                    "denoise": .75, "clip_skip": 2})
            reference = pixels() if analysis["reference_required"] else None
            request = GenerationRequest("comfyui", "workflow", "synthetic actual positive", "synthetic actual negative", config.model_dump(),
                EffectiveReference(bool(reference), "card" if reference else "none", "synthetic-reference" if reference else None))
            request = freeze_comfy_request(request)
            request = restore_generation_request(json.loads(json.dumps(asdict(request))))
            calls = []
            def handler(wire):
                calls.append((wire.method, wire.url.path))
                if wire.url.path == "/system_stats": return httpx.Response(200, json={"system": {"os": "mock"}})
                if wire.url.path == "/object_info": return httpx.Response(503)
                if wire.url.path == "/prompt":
                    actual = json.loads(wire.content)["prompt"]
                    expected = json.loads(source)
                    for position in analysis["positions"]:
                        target, value = expected[position["node_id"]]["inputs"], actual[position["node_id"]]["inputs"]
                        path = [position["input_name"], *position["path"]]
                        for key in path[:-1]: target, value = target[key], value[key]
                        target[path[-1]] = value[path[-1]]
                        if position["role"] != "reference": assert value[path[-1]] == request.comfy_execution.prepared_values[position["role"]]
                        else:
                            import base64
                            with Image.open(BytesIO(base64.b64decode(value[path[-1]], validate=True))) as image:
                                assert image.size == (128, 64) and not image.info
                    assert actual == expected  # All fixed values, links, classes and metadata unchanged.
                    return httpx.Response(200, json={"prompt_id": "mock-receipt"})
                if wire.url.path.startswith("/history/"): return httpx.Response(200, json={"mock-receipt": {"status": {"completed": True, "status_str": "success"},
                    "outputs": {"10": {"images": [{"filename": "later.png", "subfolder": "", "type": "output"}]},
                        "2": {"images": [{"filename": "preview.png", "subfolder": "", "type": "temp"}, {"filename": "batch-second.png", "subfolder": "", "type": "output"}]}}}})
                if wire.url.path == "/view":
                    assert wire.url.params["filename"] == "preview.png"
                    return httpx.Response(200, content=pixels(), headers={"content-type": "image/png"})
                raise AssertionError("Unexpected external route")
            receipts = []
            async def received(receipt): receipts.append(receipt)
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
                client = ComfyImageClient(config.base_url, ImageHttp(http))
                checked = await client.validate(config, has_reference=bool(reference))
                assert checked["ready"] and checked["candidate_lookup"]["state"] == "unavailable"
                result = await client.generate(request, None, reference, on_receipt=received)
                assert result.receipt == "mock-receipt" and receipts == ["mock-receipt"]
            assert calls.count(("POST", "/prompt")) == 1 and not any("upload" in path for _, path in calls)
            reports.append({"file": item["file"], "sha256": item["sha256"], "bytes": len(source), "nodes": len(analysis["prompt"]),
                "used_roles": analysis["used_roles"], "token_positions": len(analysis["positions"]), "original_preserved": True,
                "capture_round_trip": True, "mock_submission_and_first_image": "PASS", "actual_model_execution": "unmeasured", "ai_calls": 0,
                "source": item.get("source", item.get("url")), "commit": item.get("commit"), "blob": item.get("blob"), "copy_method": item.get("copy_method", "original downloaded bytes")})
    return reports


async def live_check(args):
    input_path = args.live_input / "angmoo-no-model.png"
    assert not input_path.exists()
    input_path.write_bytes(pixels())
    prompt = {"1": {"class_type": "LoadImage", "inputs": {"image": input_path.name}},
        "2": {"class_type": "ImageScale", "inputs": {"image": ["1", 0], "upscale_method": "nearest-exact", "width": "%width%", "height": "%height%", "crop": "disabled"}},
        "3": {"class_type": "SaveImage", "inputs": {"images": ["2", 0], "filename_prefix": "angmoo-no-model"}}}
    config = ComfyOptions(options_schema_version=2, base_url=args.live_url, workflow={"input_mode": "placeholders", "prompt": prompt}, values={"width": 64, "height": 32})
    calls, receipts = [], []
    class ObservedHttp(ImageHttp):
        async def request(self, method, url, **kwargs):
            calls.append({"method": method, "path": httpx.URL(url).path})
            return await super().request(method, url, **kwargs)
    async def received(receipt): receipts.append(receipt)
    client = ComfyImageClient(config.base_url, ObservedHttp())
    checked = await client.validate(config, has_reference=False)
    result = await client.generate(GenerationRequest("comfyui", "workflow", "unused-no-model", None, config.model_dump(), EffectiveReference(False)), None, None, on_receipt=received, timeout=60)
    with Image.open(BytesIO(result.content)) as image: assert image.size == (64, 32)
    output_path = args.output.with_name("live-result.png"); output_path.write_bytes(result.content)
    invalid = config.model_copy(update={"workflow": type(config.workflow)(input_mode="placeholders", prompt={"1": {"class_type": "AngmooMissingNodeNoInference", "inputs": {}}})})
    try:
        await client.generate(GenerationRequest("comfyui", "workflow", "unused-no-model", None, invalid.model_dump(), EffectiveReference(False)), None, None, on_receipt=received)
        raise AssertionError("Invalid node unexpectedly accepted")
    except ImageSubmissionError as error:
        assert error.code == "comfy_prompt_rejected" and not error.outcome_unknown
        rejected = {"code": error.code, "diagnostic": error.diagnostic}
    return {"connection": checked["server_connection"], "candidate_lookup": checked["candidate_lookup"], "receipt": receipts[0],
        "graph_sha256": hashlib.sha256(json.dumps(prompt, sort_keys=True).encode()).hexdigest(), "image_sha256": hashlib.sha256(result.content).hexdigest(),
        "dimensions": [64, 32], "calls": calls, "rejection": rejected, "ai_calls": 0, "model_nodes": [], "external_workflows_submitted": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official", type=Path); parser.add_argument("--community", type=Path)
    parser.add_argument("--live-url"); parser.add_argument("--live-input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(live_check(args) if args.live_url else external_checks(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "result": "PASS", "ai_calls": 0, "originals": len(result) if isinstance(result, list) else None}))


if __name__ == "__main__": main()
