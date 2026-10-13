"""V31: real ComfyUI decoder/scale/save HTTP verification, without AI models.

Use the existing CPU Python and an already acquired official node source. This
command creates a fresh owned runtime under artifacts, starts only its own
loopback server, and preserves that runtime and its evidence after stopping it.
"""
import argparse
import asyncio
import base64
from copy import deepcopy
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit

from PIL import Image

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "backend"))
from app.domains.media.generation_contracts import (
    ComfyOptions, EffectiveReference, GenerationRequest, ImageSubmissionError,
)
from app.domains.media.service.comfy_workflows import bounded_json, freeze_comfy_request
from app.integrations.comfy_images import ComfyImageClient
from app.integrations.image_api import ImageHttp

NODE_SHA = "296330305db27e8b457c7b26856dff2fb5fcdf232612a1a7b3ca3c2a85124474"
ALLOWED = {"ETN_LoadImageBase64", "ImageScale", "SaveImage"}
WEIGHT_SUFFIXES = {".ckpt", ".safetensors", ".pt", ".pth", ".bin", ".onnx", ".pkl"}


class ObservedHttp(ImageHttp):
    """Record real requests while preventing any model-bearing submission."""
    def __init__(self, base):
        super().__init__()
        self.base = base
        self.calls = []
        self.submissions = []

    async def request(self, method, url, **kwargs):
        assert url.startswith(self.base + "/")
        assert kwargs.get("key") is None
        assert "Authorization" not in kwargs.get("headers", {})
        path = urlsplit(url).path
        assert path in {"/system_stats", "/prompt", "/object_info", "/view"} or path.startswith(("/history/", "/object_info/"))
        if method == "POST":
            assert path == "/prompt"
            payload = json.loads(kwargs["content"])
            assert set(payload) == {"prompt"}
            graph = payload["prompt"]
            assert len(graph) == 3 and {node["class_type"] for node in graph.values()} == ALLOWED
            encoded = graph["8"]["inputs"]["image"]
            assert isinstance(encoded, str) and not encoded.startswith("data:")
            self.submissions.append({"classes": sorted(ALLOWED), "graph_sha256": hashlib.sha256(kwargs["content"]).hexdigest()})
        response = await super().request(method, url, **kwargs)
        self.calls.append({"method": method, "path": path, "status": response.status_code})
        return response


def sample_contract(graph, info):
    inputs = links = 0
    for node_id, node in graph.items():
        schema = info[node["class_type"]]
        fields = {**schema["input"].get("required", {}), **schema["input"].get("optional", {})}
        assert set(schema["input"].get("required", {})) <= set(node["inputs"])
        for field, value in node["inputs"].items():
            assert field in fields
            inputs += 1
            expected = fields[field][0]
            if isinstance(value, list):
                source_id, slot = value
                actual = info[graph[source_id]["class_type"]]["output"][slot]
                assert actual == expected, (node_id, field, actual, expected)
                links += 1
            elif isinstance(expected, list) and not (isinstance(value, str) and value.startswith("%") and value.endswith("%")):
                assert value in expected
    return {"registered_nodes": len(graph), "input_checks": inputs, "link_checks": links}


async def verify(base, root, process):
    http = ObservedHttp(base)
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Owned ComfyUI stopped during startup; inspect its local log")
        try:
            await http.request("GET", base + "/system_stats", timeout=2)
            break
        except ImageSubmissionError:
            await asyncio.sleep(2)
    else:
        raise TimeoutError("Owned ComfyUI startup deadline exceeded")
    print("Owned CPU ComfyUI is ready; checking real node contracts", flush=True)
    sample_root = PROJECT / "backend/app/domains/media/samples"
    samples = {kind: json.loads((sample_root / f"comfy-api-{kind}.json").read_text(encoding="utf-8")) for kind in ("text", "reference")}
    info = {}
    for name in sorted({node["class_type"] for graph in samples.values() for node in graph.values()}):
        response = await http.request("GET", base + "/object_info/" + name)
        info.update(response.json())
    assert info["ETN_LoadImageBase64"]["input"]["required"]["image"][0] == "STRING"
    assert info["ETN_LoadImageBase64"]["output"][0] == "IMAGE"
    assert info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0] == []
    contracts = {kind: sample_contract(graph, info) for kind, graph in samples.items()}

    # Retain the supplied example's decoder and scaler. Save its scaled image
    # directly; VAE/CLIP/checkpoint/sampler nodes are never submitted or executed.
    graph = {node_id: deepcopy(samples["reference"][node_id]) for node_id in ("8", "9", "7")}
    graph["7"]["inputs"]["images"] = ["9", 0]
    options = ComfyOptions(options_schema_version=2, base_url=base,
        workflow={"input_mode": "placeholders", "prompt": graph, "output": {"mode": "auto_first_image"}},
        values={"width": 64, "height": 48})
    source = (PROJECT / "backend/tests/image_integration/fixtures/comfy-reference.png").read_bytes()
    with Image.open(BytesIO(source)) as image:
        assert image.size == (16, 16) and image.getpixel((0, 0)) == (0, 255, 0)
        assert image.info
    request = freeze_comfy_request(GenerationRequest("comfyui", "workflow", "synthetic decoder check", None,
        options.model_dump(), EffectiveReference(True, "override", "synthetic-owned-png")), has_reference=True)
    receipts, submits = [], []
    async def receipt(value):
        receipts.append(value)
    async def submitted():
        submits.append(True)
    client = ComfyImageClient(base, http)
    readiness = await client.validate(options, has_reference=True)
    assert readiness["ready"]
    result = await client.generate(request, None, source, on_receipt=receipt, on_submit=submitted, timeout=60)
    assert len(receipts) == len(submits) == 1 and result.receipt == receipts[0]
    with Image.open(BytesIO(result.content)) as image:
        assert image.size == (64, 48) and image.mode == "RGB" and not image.info
        assert image.getextrema() == ((0, 0), (255, 255), (0, 0))
    (root / "decoded-result.png").write_bytes(result.content)
    successful_prompt_count = len(http.submissions)
    recovered = await client.generate(request, None, None, receipt=receipts[0], on_receipt=receipt, timeout=30)
    assert recovered.content == result.content and len(http.submissions) == successful_prompt_count
    history = (await http.request("GET", base + "/history/" + receipts[0])).json()[receipts[0]]
    executed_graph = history["prompt"][2]
    assert {node["class_type"] for node in executed_graph.values()} == ALLOWED
    decoded_input = base64.b64decode(executed_graph["8"]["inputs"]["image"], validate=True)
    with Image.open(BytesIO(decoded_input)) as image:
        assert not image.info and image.size == (16, 16)
    assert history["status"]["status_str"] == "success" and history["status"]["completed"]
    print("Actual decoder/scale/save, history/view and keyless receipt recovery passed", flush=True)

    broken_graph = deepcopy(executed_graph)
    broken_graph["9"]["inputs"]["image"] = ["missing", 0]
    rejected = await http.request("POST", base + "/prompt", content=bounded_json({"prompt": broken_graph}),
        headers={"Content-Type": "application/json"}, error_body_limit=32768)
    assert rejected.status_code == 400 and not rejected.json().get("prompt_id")

    broken_png = deepcopy(executed_graph)
    broken_png["8"]["inputs"]["image"] = base64.b64encode(b"synthetic non-PNG bytes").decode("ascii")
    accepted = await http.request("POST", base + "/prompt", content=bounded_json({"prompt": broken_png}),
        headers={"Content-Type": "application/json"}, error_body_limit=32768)
    assert accepted.status_code == 200
    failed_receipt = accepted.json()["prompt_id"]
    try:
        await client.retrieve(failed_receipt, {"mode": "auto_first_image"}, key=None, deadline=time.monotonic() + 30)
    except ImageSubmissionError as error:
        assert error.code == "comfy_execution_failed" and not error.outcome_unknown
    else:
        raise AssertionError("Actual malformed PNG must fail, without an image result")
    failed_history = (await http.request("GET", base + "/history/" + failed_receipt)).json()[failed_receipt]
    assert failed_history["status"]["status_str"] == "error" and not failed_history["outputs"]
    assert len(list((root / "output").rglob("*.png"))) == 1
    assert all(entry["path"] != "/upload/image" for entry in http.calls)
    return {"sample_contracts": contracts, "decoder_contract": "STRING image -> IMAGE slot 0",
        "positive": {"status": "passed", "receipt": receipts[0], "source_pixels": [16, 16],
            "result_pixels": [64, 48], "rgb": [0, 255, 0], "metadata_stripped": True,
            "result_sha256": hashlib.sha256(result.content).hexdigest(), "receipt_recovery_new_prompt_count": 0},
        "negative": {"dangling_link": "HTTP 400, no receipt", "invalid_png": "comfy_execution_failed, no output"},
        "submissions": http.submissions, "http_calls": http.calls, "model_nodes_submitted": 0,
        "model_files": 0, "gpu_inference": False, "paid_provider_calls": 0, "real_comfy_http": True,
        "full_example_ai_generation": "excluded by user instruction"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy-root", required=True, type=Path)
    parser.add_argument("--node-source", required=True, type=Path)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--port", default=18290, type=int)
    args = parser.parse_args()
    root, comfy, node = args.run_root.resolve(), args.comfy_root.resolve(), args.node_source.resolve()
    if (PROJECT / "artifacts").resolve() not in root.parents or root.exists():
        raise ValueError("A fresh owned artifacts run root is required")
    if hashlib.sha256((node / "nodes.py").read_bytes()).hexdigest() != NODE_SHA:
        raise ValueError("The inspected official decoder revision is required")
    if (comfy / "extra_model_paths.yaml").exists():
        raise ValueError("External model paths are excluded from this verification")
    if any(path.is_symlink() or path.suffix.lower() in WEIGHT_SUFFIXES for path in node.rglob("*")):
        raise ValueError("Node source must not contain links or AI model artifacts")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", args.port))
    root.mkdir(parents=True)
    (root / "owned-model-free-runtime.json").write_text('{"purpose":"V31 decoder only","models":false}\n', encoding="utf-8")
    for directory in ("input", "output", "temp", "user", "models"):
        (root / directory).mkdir()
    shutil.copytree(node, root / "custom_nodes/comfyui-tooling-nodes")
    python = comfy / ".venv/Scripts/python.exe"
    subprocess.run([str(python), "-I", "-c",
        "import importlib.util; assert importlib.util.find_spec('argostranslate') is None"],
        check=True, capture_output=True, timeout=15)
    frontend = comfy / ".venv/Lib/site-packages/comfyui_frontend_package/static"
    command = [str(python), "-u", str(comfy / "main.py"), "--listen", "127.0.0.1", "--port", str(args.port),
        "--cpu", "--disable-auto-launch", "--disable-all-custom-nodes", "--whitelist-custom-nodes", "comfyui-tooling-nodes",
        "--disable-api-nodes", "--disable-metadata", "--cache-none", "--base-directory", str(root),
        "--models-directory", str(root / "models"), "--user-directory", str(root / "user"),
        "--database-url", "sqlite:///" + (root / "user/comfyui.db").as_posix(), "--front-end-root", str(frontend)]
    environment = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
        DO_NOT_TRACK="1", CUDA_VISIBLE_DEVICES="")
    hidden = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    report = {"status": "failed", "runtime_root": str(root), "comfy_root": str(comfy), "node_source_sha256": NODE_SHA}
    with (root / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=comfy, env=environment, stdout=log, stderr=subprocess.STDOUT, creationflags=hidden)
        report["owned_process_pid"] = process.pid
        try:
            report.update(asyncio.run(verify(f"http://127.0.0.1:{args.port}", root, process)))
            report["status"] = "passed"
        finally:
            if process.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, timeout=15, creationflags=hidden, check=False)
                else:
                    process.terminate()
                process.wait(timeout=15)
            with socket.socket() as probe:
                report["owned_port_released"] = probe.connect_ex(("127.0.0.1", args.port)) != 0
            report["remaining_model_files"] = len([path for path in root.rglob("*")
                if path.is_file() and path.suffix.lower() in WEIGHT_SUFFIXES])
            (root / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    assert report["owned_port_released"] and report["remaining_model_files"] == 0
    print(json.dumps({"status": report["status"], "report": str(root / "report.json"),
        "checks": ["actual decoder/scale/save", "metadata strip", "HTTP/history/view", "receipt recovery",
                   "dangling-link rejection", "malformed PNG failure", "sample node contracts"], "AI_model_calls": 0}), flush=True)


if __name__ == "__main__":
    main()
