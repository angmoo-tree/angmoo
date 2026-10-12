"""Independently authored API graphs; does not access ComfyUI or install models."""
import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "backend/app/domains/media/samples"


def node(kind, **inputs):
    return {"class_type": kind, "inputs": inputs}


def make(reference=False):
    prompt = {"1": node("CheckpointLoaderSimple", ckpt_name="choose-installed-model.safetensors"),
        "2": node("CLIPTextEncode", text="", clip=["1", 1]),
        "3": node("CLIPTextEncode", text="", clip=["1", 1]),
        "4": node("KSampler", model=["1", 0], positive=["2", 0], negative=["3", 0], latent_image=["5", 0],
            seed=0, steps=20, cfg=7.0, sampler_name="euler", scheduler="normal", denoise=1.0),
        "5": node("EmptyLatentImage", width=512, height=512, batch_size=1),
        "6": node("VAEDecode", samples=["4", 0], vae=["1", 2]),
        "7": node("SaveImage", images=["6", 0], filename_prefix="Angmoo")}
    positions = {"positive": ("2", "text"), "negative": ("3", "text"), "width": ("5", "width"),
        "height": ("5", "height"), "model": ("1", "ckpt_name"), "steps": ("4", "steps"), "cfg": ("4", "cfg"),
        "seed": ("4", "seed"), "sampler": ("4", "sampler_name"), "scheduler": ("4", "scheduler"), "denoise": ("4", "denoise")}
    if reference:
        prompt["5"] = node("VAEEncode", pixels=["9", 0], vae=["1", 2])
        prompt["8"] = node("LoadImage", image="uploaded-by-angmoo.png")
        prompt["9"] = node("ImageScale", image=["8", 0], upscale_method="lanczos", width=512, height=512, crop="disabled")
        positions.update(reference=("8", "image"), width=("9", "width"), height=("9", "height"))
    bindings = {field: {"node_id": position[0], "input_name": position[1]} for field, position in positions.items()}
    values = {field: prompt[position[0]]["inputs"][position[1]] for field, position in positions.items()
        if field not in {"positive", "negative", "reference"}}
    return {"workflow": {"prompt": prompt, "bindings": bindings, "output_node": "7", "reference_required": reference},
        "values": values, "dependencies": {"nodes": sorted({value["class_type"] for value in prompt.values()}),
            "models": ["사용자가 서버에 준비한 호환 checkpoint"], "reference_method": "image-to-image" if reference else "text-to-image",
            "source": "Angmoo independently authored API graph", "docs": "https://docs.comfy.org/development/comfyui-server/comms_routes"}}


def make_api(reference=False):
    """Keep the historical config builder intact; export just an API graph."""
    sample = make(reference)
    graph = deepcopy(sample["workflow"]["prompt"])
    tokens = {"positive": "%prompt%", "negative": "%negative_prompt%", "model": "%model%",
        "width": "%width%", "height": "%height%", "steps": "%steps%", "cfg": "%scale%",
        "sampler": "%sampler%", "scheduler": "%scheduler%", "seed": "%seed%",
        "denoise": "%denoise%", "reference": "%char_avatar%"}
    for role, binding in sample["workflow"]["bindings"].items():
        graph[binding["node_id"]]["inputs"][binding["input_name"]] = tokens[role]
    if reference:
        graph["8"]["class_type"] = "ETN_LoadImageBase64"
    return graph


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format",choices=("config","api_json"),default="config")
    selected=parser.parse_args().format
    ROOT.mkdir(parents=True, exist_ok=True)
    for reference in (False, True):
        name=f"comfy-{'api-' if selected=='api_json' else ''}{'reference' if reference else 'text'}.json"
        content=json.dumps(make_api(reference) if selected=='api_json' else make(reference), ensure_ascii=False, indent=2) + "\n"
        if selected=='api_json':(ROOT / name).write_bytes(content.encode("utf-8"))
        else:(ROOT / name).write_text(content,"utf-8")
    print("Authored text and reference samples. No model installation or API call.")
