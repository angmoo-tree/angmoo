"""Typed workflow injection and receipt-based ComfyUI execution."""
import asyncio
import copy
import ipaddress
import math
import time
from urllib.parse import urlsplit
from app.domains.media.generation_contracts import ComfyWorkflow, ImagePreparationError, ImageSubmissionError, ImageResult
from app.integrations.image_api import ImageHttp
from app.integrations.media.images import validate_generated_media_content, inspect_image_bytes, ImageBytesError

BINDING_FIELDS = {"positive", "negative", "width", "height", "steps", "cfg", "sampler", "scheduler", "seed", "denoise", "model", "vae", "clip_skip", "reference"}


def validate_base_url(value):
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ImagePreparationError("comfy_url_invalid")
    if parsed.scheme == "http":
        try:
            address = ipaddress.ip_address(parsed.hostname)
            loopback = address.is_loopback or (address.is_private and not address.is_link_local and not address.is_unspecified)
        except ValueError:
            loopback = parsed.hostname == "localhost"
        if not loopback:
            raise ImagePreparationError("comfy_remote_requires_https")
    return value.rstrip("/")


def _input_spec(info, node, name):
    class_type = node.get("class_type")
    definition = info.get(class_type)
    if not isinstance(definition, dict):
        raise ImagePreparationError("comfy_node_missing")
    inputs = definition.get("input", {})
    spec = inputs.get("required", {}).get(name) or inputs.get("optional", {}).get(name)
    if not isinstance(spec, (list, tuple)) or not spec:
        raise ImagePreparationError("comfy_input_missing")
    return spec


def _validate_value(spec, value):
    kind = spec[0]
    if isinstance(kind, list):
        if value not in kind:
            raise ImagePreparationError("comfy_input_choice_invalid")
    elif kind == "INT":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ImagePreparationError("comfy_input_type_invalid")
    elif kind == "FLOAT":
        if not isinstance(value, (float, int)) or isinstance(value, bool) or not math.isfinite(value):
            raise ImagePreparationError("comfy_input_type_invalid")
    elif kind == "STRING":
        if not isinstance(value, str):
            raise ImagePreparationError("comfy_input_type_invalid")
    elif kind == "BOOLEAN":
        if not isinstance(value, bool):
            raise ImagePreparationError("comfy_input_type_invalid")
    else:
        raise ImagePreparationError("comfy_binding_not_scalar")
    limits = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
    if isinstance(value, (int, float)) and (value < limits.get("min", float("-inf")) or value > limits.get("max", float("inf"))):
        raise ImagePreparationError("comfy_input_out_of_range")


def validate_workflow(workflow: ComfyWorkflow, info, values=None):
    if not workflow.prompt or len(workflow.prompt) > 256:
        raise ImagePreparationError("comfy_workflow_size_invalid")
    bound = {(value.node_id, value.input_name) for value in workflow.bindings.values()}
    for node_id, node in workflow.prompt.items():
        if node.get("class_type") not in info or not isinstance(node.get("inputs"), dict):
            raise ImagePreparationError("comfy_dependency_missing")
        definition = info[node["class_type"]]
        for name in definition.get("input", {}).get("required", {}):
            if name not in node["inputs"]:
                raise ImagePreparationError("comfy_required_input_missing")
        for name, value in node["inputs"].items():
            spec = _input_spec(info, node, name)
            if any(secret in name.lower() for secret in ("api_key", "token", "password", "secret")) and value:
                raise ImagePreparationError("comfy_workflow_contains_secret")
            if (node_id, name) in bound:
                continue
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and isinstance(value[1], int):
                source = workflow.prompt.get(value[0])
                outputs = info.get(source.get("class_type"), {}).get("output", []) if source else []
                if value[1] < 0 or value[1] >= len(outputs) or (spec[0] != "*" and outputs[value[1]] != spec[0]):
                    raise ImagePreparationError("comfy_link_invalid")
            elif isinstance(spec[0], list) or spec[0] in {"INT", "FLOAT", "STRING", "BOOLEAN"}:
                _validate_value(spec, value)
            else:
                raise ImagePreparationError("comfy_link_required")
    if "positive" not in workflow.bindings or not set(workflow.bindings).issubset(BINDING_FIELDS):
        raise ImagePreparationError("comfy_bindings_invalid")
    positions = set()
    for field, binding in workflow.bindings.items():
        position = (binding.node_id, binding.input_name)
        if position in positions:
            raise ImagePreparationError("comfy_binding_collision")
        positions.add(position)
        node = workflow.prompt.get(binding.node_id)
        if node is None or binding.input_name not in node.get("inputs", {}):
            raise ImagePreparationError("comfy_binding_missing")
        spec = _input_spec(info, node, binding.input_name)
        scalar_type = {"positive": "STRING", "negative": "STRING", "width": "INT", "height": "INT",
            "steps": "INT", "seed": "INT", "clip_skip": "INT", "cfg": "FLOAT", "denoise": "FLOAT"}.get(field)
        if scalar_type is not None and spec[0] != scalar_type:
            raise ImagePreparationError("comfy_binding_type_invalid")
        if field == "reference":
            # LoadImage choices are uploaded filenames; do not require a sample file to exist.
            if node["class_type"] != "LoadImage" or binding.input_name != "image":
                raise ImagePreparationError("comfy_reference_loader_unsupported")
        else:
            original = values[field] if values is not None and field in values else node["inputs"][binding.input_name]
            if field == "seed" and original == -1:
                original = 0
            _validate_value(spec, original)
    output = workflow.prompt.get(workflow.output_node)
    if not output or not info[output["class_type"]].get("output_node"):
        raise ImagePreparationError("comfy_output_invalid")
    if not any(spec[0] == "IMAGE" for spec in info[output["class_type"]].get("input", {}).get("required", {}).values()):
        raise ImagePreparationError("comfy_output_not_image")
    if workflow.reference_required != ("reference" in workflow.bindings):
        raise ImagePreparationError("comfy_reference_contract_invalid")


def inject_workflow(workflow, info, values):
    validate_workflow(workflow, info, values)
    if set(values) - set(workflow.bindings):
        raise ImagePreparationError("comfy_value_unbound")
    result = copy.deepcopy(workflow.prompt)
    for name, value in values.items():
        binding = workflow.bindings[name]
        result[binding.node_id]["inputs"][binding.input_name] = value
    return result


class ComfyImageClient:
    def __init__(self, base_url, http=None):
        self.base = validate_base_url(base_url)
        self.http = http or ImageHttp()

    async def validate(self, options, key=None):
        info = (await self.http.request("GET", self.base + "/object_info", key=key)).json()
        workflow = options.workflow
        if workflow is None:
            raise ImagePreparationError("comfy_workflow_required")
        validation_values = {name: 0 if name == "seed" and value == -1 else value for name, value in options.values.items()}
        validate_workflow(workflow, info, validation_values)
        if options.text_workflow:
            validate_workflow(options.text_workflow, info, validation_values)
            if options.text_workflow.reference_required:
                raise ImagePreparationError("comfy_text_workflow_requires_reference")
        for graph in (options.workflow, options.text_workflow):
            if graph is None:
                continue
            partner = any(info[node["class_type"]].get("api_node") or info[node["class_type"]].get("is_api_node")
                for node in graph.prompt.values())
            if partner != options.partner_auth:
                raise ImagePreparationError("comfy_partner_auth_required" if partner else "comfy_partner_workflow_required")
        if set(options.values) - set(workflow.bindings) or (options.text_workflow and set(options.values) - set(options.text_workflow.bindings)):
            raise ImagePreparationError("comfy_value_unbound")
        return info

    async def generate(self, request, key, reference, *, on_receipt, receipt=None, timeout=120.0, on_submit=None, partner_key=None):
        from app.domains.media.generation_contracts import ComfyOptions
        options = ComfyOptions.model_validate(request.options)
        if options.partner_auth and not partner_key:
            raise ImagePreparationError("comfy_partner_key_required")
        workflow = options.workflow
        if workflow is None:
            raise ImagePreparationError("comfy_workflow_required")
        if workflow.reference_required and reference is None:
            workflow = options.text_workflow
            if workflow is None:
                raise ImagePreparationError("comfy_reference_or_text_path_required")
        deadline = time.monotonic() + timeout
        if receipt is None:
            info = await self.validate(options, key)
            values = {**options.values, "positive": request.positive}
            if "negative" in workflow.bindings:
                values["negative"] = request.negative or ""
            if "seed" in workflow.bindings and values.get("seed", -1) == -1:
                import secrets
                values["seed"] = secrets.randbits(32)
            if reference is not None and "reference" in workflow.bindings:
                try:
                    reference_info = inspect_image_bytes(reference, max_bytes=10 * 1024 * 1024)
                except ImageBytesError as exc:
                    raise ImagePreparationError("reference_pixels_invalid") from exc
                upload = await self.http.request("POST", self.base + "/upload/image", key=key,
                    files={"image": (f"angmoo-reference.{reference_info.extension}", reference, reference_info.content_type)}, data={"type": "input", "overwrite": "false"})
                payload = upload.json()
                filename, folder = payload.get("name"), payload.get("subfolder", "")
                if not isinstance(filename, str) or not filename or len(filename) > 255 or filename in {".", ".."} or "/" in filename or "\\" in filename or ":" in filename or not isinstance(folder, str) or len(folder) > 255 or folder.startswith("/") or "\\" in folder or ":" in folder or ".." in folder.split("/"):
                    raise ImagePreparationError("comfy_upload_response_invalid")
                values["reference"] = f"{folder}/{filename}" if folder else filename
            graph = inject_workflow(workflow, info, values)
            if on_submit:
                await on_submit()
            payload = {"prompt": graph}
            if options.partner_auth:
                payload["extra_data"] = {"api_key_comfy_org": partner_key}
            response = await self.http.request("POST", self.base + "/prompt", key=key, json=payload)
            payload = response.json()
            receipt = payload.get("prompt_id")
            if payload.get("node_errors") or not isinstance(receipt, str) or not receipt or len(receipt) > 160:
                raise ImageSubmissionError("comfy_prompt_rejected")
            await on_receipt(receipt)
        try:
            return await self.retrieve(receipt, workflow.output_node, key=key, deadline=deadline)
        except ImageSubmissionError as exc:
            raise ImageSubmissionError(exc.code, outcome_unknown=exc.code != "comfy_execution_failed", receipt=receipt) from exc

    async def retrieve(self, receipt, output_node, *, key, deadline):
        from urllib.parse import quote
        while time.monotonic() < deadline:
            history = (await self.http.request("GET", self.base + "/history/" + quote(receipt, safe=""), key=key, timeout=min(15, max(1, deadline - time.monotonic())))).json()
            item = history.get(receipt)
            if item:
                if item.get("status", {}).get("status_str") == "error":
                    raise ImageSubmissionError("comfy_execution_failed")
                images = item.get("outputs", {}).get(output_node, {}).get("images", [])
                if images:
                    if len(images) != 1 or images[0].get("type") not in {"output", "temp"}:
                        raise ImageSubmissionError("comfy_output_shape_invalid")
                    name, folder = images[0].get("filename"), images[0].get("subfolder", "")
                    if not isinstance(name, str) or not name or any(c in name for c in ("/", "\\", ":")) or name in {".", ".."} or not isinstance(folder, str) or folder.startswith("/") or any(c in folder for c in ("\\", ":")) or ".." in folder.split("/"):
                        raise ImageSubmissionError("comfy_output_shape_invalid")
                    response = await self.http.request("GET", self.base + "/view", key=key,
                        params={"filename": name, "subfolder": folder, "type": images[0]["type"]})
                    mime = response.headers.get("content-type", "").split(";")[0]
                    validate_generated_media_content(mime, response.content, max_bytes=12 * 1024 * 1024)
                    return ImageResult(response.content, mime, receipt=receipt)
            await asyncio.sleep(min(1.0, max(0, deadline - time.monotonic())))
        raise ImageSubmissionError("comfy_history_timeout", outcome_unknown=True, receipt=receipt)
