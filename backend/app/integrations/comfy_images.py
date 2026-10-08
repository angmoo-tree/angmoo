"""App input contracts, ComfyUI graph validation and receipt-based execution."""
import asyncio
import base64
import hashlib
import time
from dataclasses import replace
from io import BytesIO
from urllib.parse import quote

from PIL import Image
from app.domains.media.generation_contracts import (ComfyOptions, ComfyWorkflow, PlaceholderWorkflow,
    ImagePreparationError, ImageSubmissionError, ImageResult)
from app.domains.media.service.comfy_workflows import (analyze_graph, bounded_json, freeze_comfy_request,
    output_policy, prepare_values, render_workflow, required_roles, select_comfy_workflow, validate_app_workflow, validate_base_url, TOKENS)
from app.integrations.image_api import ImageHttp
from app.integrations.comfy_diagnostics import diagnostic
from app.integrations.media.images import validate_generated_media_content
from app.core.image_bytes import inspect_image_bytes, ImageBytesError

BINDING_FIELDS = set(TOKENS.values())


def validate_workflow(workflow, info=None, values=None):
    """Historical callable enforces app locations, never server node types."""
    validate_app_workflow(workflow)


def inject_workflow(workflow, info, values):
    return render_workflow(workflow, values)


def javascript_keys(mapping):
    indices, other = [], []
    for key in mapping:
        if isinstance(key, str) and key.isascii() and key.isdigit() and str(int(key)) == key and int(key) < 4294967295:
            indices.append(key)
        else:
            other.append(key)
    return sorted(indices, key=int) + other


def select_image(outputs, policy):
    if not isinstance(outputs, dict):
        raise ImageSubmissionError("comfy_output_shape_invalid", stage="output")
    keys = javascript_keys(outputs) if policy["mode"] == "auto_first_image" else [policy["node_id"]]
    for key in keys:
        node = outputs.get(key)
        images = node.get("images") if isinstance(node, dict) else None
        if images is None or images == []:
            continue
        if not isinstance(images, list) or (policy["mode"] == "legacy_single" and len(images) != 1):
            raise ImageSubmissionError("comfy_output_shape_invalid", stage="output")
        return images[0]
    raise ImageSubmissionError("comfy_no_image_output" if policy["mode"] == "auto_first_image" else "comfy_selected_output_missing", stage="output")


def reference_png(content):
    try:
        inspect_image_bytes(content, max_bytes=10 * 1024 * 1024)
        with Image.open(BytesIO(content)) as image:
            pixels = Image.new("RGBA" if "A" in image.getbands() else "RGB", image.size)
            pixels.paste(image.convert(pixels.mode))
            output = BytesIO()
            pixels.save(output, "PNG")
        normalized = output.getvalue()
        inspect_image_bytes(normalized, max_bytes=10 * 1024 * 1024, declared_mime="image/png")
    except (ImageBytesError, OSError, ValueError) as exc:
        raise ImagePreparationError("reference_pixels_invalid") from exc
    return normalized


def reference_base64(content):
    return base64.b64encode(reference_png(content)).decode("ascii")


class ComfyImageClient:
    def __init__(self, base_url, http=None):
        self.base = validate_base_url(base_url)
        self.http = http or ImageHttp()

    async def validate(self, options, key=None, *, has_reference=True):
        if options.workflow is None:
            raise ImagePreparationError("comfy_workflow_required")
        analyses = {}
        for path, graph in (("workflow", options.workflow), ("text_workflow", options.text_workflow)):
            if graph is not None:
                validate_app_workflow(graph)
                roles = required_roles(graph)
                if path == "text_workflow" and "reference" in roles:
                    raise ImagePreparationError("comfy_text_workflow_requires_reference")
                analyses[path] = {**analyze_graph(graph.prompt), "used_roles": sorted(roles),
                    "reference_required": "reference" in roles, "prompt_applied": "positive" in roles}
                analyses[path].pop("prompt")
        selected = select_comfy_workflow(options, has_reference=has_reference)
        prepare_values(options, selected)
        stats = await self.http.request("GET", self.base + "/system_stats", key=key)
        try:
            if not isinstance(stats.json(), dict):
                raise ValueError()
        except ValueError as exc:
            raise ImagePreparationError("comfy_connection_invalid") from exc
        info, lookup = {}, {"state": "unavailable", "reason": "comfy_candidate_unavailable"}
        try:
            candidate = (await self.http.request("GET", self.base + "/object_info", key=key)).json()
            if isinstance(candidate, dict):
                info = {name: value for name, value in candidate.items() if isinstance(value, dict) and isinstance(value.get("input"), dict)}
                lookup = {"state": "available" if info and len(info) == len(candidate) else "partial", "reason": None}
        except (ImageSubmissionError, ValueError, TypeError):
            pass
        return {"object_info": info, "candidate_lookup": lookup, "workflow_analysis": analyses,
            "server_connection": {"state": "connected"},
            "input_readiness": {"state": "ready", "path": "workflow" if selected is options.workflow else "text_workflow"},
            "reference_supported": "reference" in required_roles(options.workflow), "ready": True}

    async def generate(self, request, key, reference, *, on_receipt, receipt=None, timeout=120.0, on_submit=None, partner_key=None, on_diagnostic=None):
        options = ComfyOptions.model_validate(request.options)
        if options.partner_auth and not partner_key:
            raise ImagePreparationError("comfy_partner_key_required")
        deadline = time.monotonic() + timeout
        warning = None
        sensitive = [key, partner_key, request.positive, request.negative]
        if receipt is None:
            request = freeze_comfy_request(request, has_reference=reference is not None)
            snapshot = request.comfy_execution
            workflow = getattr(options, snapshot.selected_path)
            input_mode = "legacy_bindings" if isinstance(workflow, ComfyWorkflow) else getattr(workflow, "input_mode", None)
            if workflow is None or hashlib.sha256(bounded_json(workflow.prompt)).hexdigest() != snapshot.graph_digest or snapshot.base_url != options.base_url or snapshot.output != output_policy(workflow) or snapshot.input_mode != input_mode or snapshot.options_schema_version != options.options_schema_version:
                raise ImagePreparationError("comfy_execution_snapshot_invalid")
            values = dict(snapshot.prepared_values)
            if "reference" in required_roles(workflow):
                if reference is None:
                    raise ImagePreparationError("comfy_reference_or_text_path_required")
                if isinstance(workflow, PlaceholderWorkflow):
                    values["reference"] = reference_base64(reference)
                    sensitive.append(values["reference"])
                else:
                    info = inspect_image_bytes(reference, max_bytes=10 * 1024 * 1024)
                    upload = await self.http.request("POST", self.base + "/upload/image", key=key,
                        files={"image": (f"angmoo-reference.{info.extension}", reference, info.content_type)}, data={"type": "input", "overwrite": "false"})
                    payload = upload.json()
                    filename, folder = payload.get("name"), payload.get("subfolder", "")
                    self._descriptor({"filename": filename, "subfolder": folder, "type": "input"}, upload=True)
                    values["reference"] = f"{folder}/{filename}" if folder else filename
            graph = render_workflow(workflow, values)
            payload = {"prompt": graph}
            if options.partner_auth:
                payload["extra_data"] = {"api_key_comfy_org": partner_key}
            body = bounded_json(payload)
            if on_submit:
                await on_submit()
            response = await self.http.request("POST", self.base + "/prompt", key=key, content=body,
                headers={"Content-Type": "application/json"}, error_body_limit=32 * 1024)
            try:
                payload = response.json()
            except ValueError as exc:
                known_rejection = 400 <= response.status_code < 500
                raise ImageSubmissionError("comfy_prompt_rejected" if known_rejection else "comfy_prompt_response_invalid", outcome_unknown=not known_rejection, stage="submission",
                    diagnostic=diagnostic({}, stage="submission", truncated=bool(response.extensions.get("angmoo_body_truncated")))) from exc
            receipt = payload.get("prompt_id") if isinstance(payload, dict) else None
            if isinstance(receipt, str) and receipt and len(receipt) <= 160:
                await on_receipt(receipt)
                if payload.get("node_errors") or payload.get("error"):
                    warning = diagnostic(payload, stage="submission", kind="warning", sensitive=sensitive)
                    if on_diagnostic:
                        await on_diagnostic(warning)
            else:
                raise ImageSubmissionError("comfy_prompt_rejected", outcome_unknown=response.status_code >= 500 or (response.status_code < 400 and not (isinstance(payload, dict) and (payload.get("error") or payload.get("node_errors")))), stage="submission",
                    diagnostic=diagnostic(payload, stage="submission", sensitive=sensitive, truncated=bool(response.extensions.get("angmoo_body_truncated"))))
            policy = snapshot.output
        else:
            policy = request.comfy_execution.output if request.comfy_execution else output_policy(options.workflow)
        try:
            result = await self.retrieve(receipt, policy, key=key, deadline=deadline, sensitive=sensitive)
            return replace(result, diagnostic=warning)
        except ImageSubmissionError as exc:
            terminal = exc.code in {"comfy_execution_failed", "comfy_no_image_output", "comfy_selected_output_missing", "comfy_output_shape_invalid", "generated_media_invalid"}
            raise ImageSubmissionError(exc.code, outcome_unknown=exc.outcome_unknown or not terminal, receipt=receipt, stage=exc.stage,
                diagnostic=exc.diagnostic or warning) from exc

    @staticmethod
    def _descriptor(image, upload=False):
        if not isinstance(image, dict):
            raise ImageSubmissionError("comfy_output_shape_invalid", stage="output")
        name, folder = image.get("filename"), image.get("subfolder", "")
        if image.get("type") not in ({"input"} if upload else {"output", "temp"}) or not isinstance(name, str) or not name or len(name) > 255 or any(c in name for c in ("/", "\\", ":", "\x00")) or name in {".", ".."} or not isinstance(folder, str) or len(folder) > 255 or folder.startswith("/") or any(c in folder for c in ("\\", ":", "\x00")) or ".." in folder.split("/"):
            raise ImageSubmissionError("comfy_upload_response_invalid" if upload else "comfy_output_shape_invalid", stage="output")
        return name, folder

    async def retrieve(self, receipt, output_node, *, key, deadline, sensitive=()):
        policy = {"mode": "legacy_single", "node_id": output_node} if isinstance(output_node, str) else output_node
        while time.monotonic() < deadline:
            response = await self.http.request("GET", self.base + "/history/" + quote(receipt, safe=""), key=key, timeout=min(15, max(1, deadline - time.monotonic())))
            try:
                history = response.json()
                item = history.get(receipt) if isinstance(history, dict) else None
            except ValueError as exc:
                raise ImageSubmissionError("comfy_history_invalid", outcome_unknown=True, stage="history") from exc
            if isinstance(item, dict):
                status = item.get("status", {})
                if not isinstance(status, dict) or not isinstance(status.get("messages", []), list):
                    raise ImageSubmissionError("comfy_history_invalid", outcome_unknown=True, stage="history")
                if status.get("status_str") == "error" or any(isinstance(message, list) and message and message[0] == "execution_error" for message in status.get("messages", [])):
                    raise ImageSubmissionError("comfy_execution_failed", stage="execution", diagnostic=diagnostic(item, stage="execution", sensitive=sensitive))
                outputs = item.get("outputs", {})
                completed = status.get("completed") is True or status.get("status_str") == "success"
                if completed or ("status" not in item and outputs):
                    image = select_image(outputs, policy)
                    name, folder = self._descriptor(image)
                    response = await self.http.request("GET", self.base + "/view", key=key,
                        params={"filename": name, "subfolder": folder, "type": image["type"]})
                    mime = response.headers.get("content-type", "").split(";")[0]
                    try:
                        validate_generated_media_content(mime, response.content, max_bytes=12 * 1024 * 1024)
                    except ValueError as exc:
                        raise ImageSubmissionError("generated_media_invalid", stage="output") from exc
                    return ImageResult(response.content, mime, receipt=receipt)
            await asyncio.sleep(min(1.0, max(0, deadline - time.monotonic())))
        raise ImageSubmissionError("comfy_history_timeout", outcome_unknown=True, receipt=receipt, stage="history")
