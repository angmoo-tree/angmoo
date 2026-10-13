"""App-owned JSON/value contracts. ComfyUI alone validates graph execution."""
from __future__ import annotations

import copy
import hashlib
import json
import ipaddress
import math
import secrets
from dataclasses import replace
from urllib.parse import urlsplit, urlunsplit

from ..generation_contracts import (BoundWorkflow, ComfyExecution, ComfyOptions,
    ComfyWorkflow, EffectiveReference, GenerationRequest, ImagePreparationError,
    PlaceholderWorkflow, WorkflowInput)

MAX_GRAPH_BYTES = 2 * 1024 * 1024
MAX_SUBMIT_BYTES = 32 * 1024 * 1024
MAX_DEPTH = 64
MAX_ITEMS = 100_000
TOKENS = dict(zip(("%prompt%", "%negative_prompt%", "%model%", "%vae%", "%width%",
    "%height%", "%steps%", "%scale%", "%sampler%", "%scheduler%", "%seed%",
    "%denoise%", "%clip_skip%", "%char_avatar%"), ("positive", "negative", "model",
    "vae", "width", "height", "steps", "cfg", "sampler", "scheduler", "seed",
    "denoise", "clip_skip", "reference")))
INT_ROLES = {"width", "height", "steps", "seed", "clip_skip"}
NUMBER_ROLES = {"cfg", "denoise"}


def validate_base_url(value):
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ImagePreparationError("comfy_url_invalid") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment or (port is not None and not 1 <= port <= 65535) or any(char.isspace() for char in value):
        raise ImagePreparationError("comfy_url_invalid")
    return value.rstrip("/")


def partner_submission_target(value: str, partner_auth: bool) -> str:
    """Classify the actual new-submission target without changing saved URLs."""
    base = validate_base_url(value)
    if not partner_auth:
        return base
    parsed = urlsplit(base)
    if parsed.scheme == "https":
        return base
    if parsed.hostname == "localhost":
        host = "127.0.0.1" + (f":{parsed.port}" if parsed.port is not None else "")
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        address = None
    if address is not None and ((address.version == 4 and address.is_loopback) or address == ipaddress.IPv6Address("::1")):
        return base
    raise ImagePreparationError("comfy_partner_https_required")


def validate_partner_configuration(options, *, previous, auto_enabled, new_key=False):
    """A historical OFF profile may be read/cleared, but never newly activated."""
    if not options.partner_auth:
        return
    unchanged_off = (not auto_enabled and not new_key and previous is not None
        and previous.get("active") is True
        and ComfyOptions.model_validate(previous.get("options", {})).model_dump(exclude_none=True) == options.model_dump(exclude_none=True))
    if not unchanged_off:
        partner_submission_target(options.base_url, True)


def bounded_json(value, *, limit=MAX_SUBMIT_BYTES):
    buffer = bytearray()
    try:
        for piece in json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(",", ":")).iterencode(value):
            encoded = piece.encode("utf-8")
            if len(buffer) + len(encoded) > limit:
                raise ImagePreparationError("comfy_payload_too_large")
            buffer.extend(encoded)
    except (ValueError, RecursionError, UnicodeError) as exc:
        if isinstance(exc, ImagePreparationError):
            raise
        raise ImagePreparationError("comfy_json_invalid") from exc
    return bytes(buffer)


def check_tree(value):
    stack = [(value, 0)]
    count = 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if count > MAX_ITEMS or depth > MAX_DEPTH:
            raise ImagePreparationError("comfy_json_complexity_exceeded")
        if isinstance(item, dict):
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
        elif isinstance(item, float) and not math.isfinite(item):
            raise ImagePreparationError("comfy_value_invalid")


def strict_json(source, *, limit=MAX_GRAPH_BYTES):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ImagePreparationError("comfy_json_duplicate_key")
            result[key] = value
        return result
    def invalid_constant(_):
        raise ImagePreparationError("comfy_json_invalid")
    try:
        if len(source.encode("utf-8")) > limit:
            raise ImagePreparationError("comfy_workflow_size_invalid")
        value = json.loads(source, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (ValueError, RecursionError, UnicodeError) as exc:
        if isinstance(exc, ImagePreparationError):
            raise
        raise ImagePreparationError("comfy_json_invalid") from exc
    check_tree(value)
    return value


def validate_graph(graph):
    check_tree(graph)
    bounded_json(graph, limit=MAX_GRAPH_BYTES)
    if not isinstance(graph, dict) or not graph or len(graph) > 256:
        raise ImagePreparationError("comfy_workflow_size_invalid")
    for key, node in graph.items():
        if not isinstance(key, str) or not key or not isinstance(node, dict) or not isinstance(node.get("class_type"), str) or not node["class_type"] or not isinstance(node.get("inputs"), dict):
            raise ImagePreparationError("comfy_api_graph_required")


def is_link(value):
    return isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and type(value[1]) is int


def analyze_graph(graph, *, source_json=None):
    validate_graph(graph)
    positions, notices = [], []
    for node_id, node in graph.items():
        stack = [(name, [], value) for name, value in node["inputs"].items()]
        while stack:
            input_name, path, value = stack.pop()
            if isinstance(value, str):
                if value in TOKENS:
                    positions.append({"token": value, "role": TOKENS[value], "node_id": node_id,
                        "input_name": input_name, "path": path})
                elif "%" in value:
                    notices.append({"node_id": node_id, "input_name": input_name, "path": path,
                        "kind": "preserved_expression"})
            elif isinstance(value, dict):
                stack.extend((input_name, [*path, name], child) for name, child in value.items())
            elif isinstance(value, list) and not is_link(value):
                stack.extend((input_name, [*path, index], child) for index, child in enumerate(value))
    roles = sorted({item["role"] for item in positions})
    return {"prompt": graph, "supported_tokens": TOKENS, "positions": positions,
        "notices": notices, "used_roles": roles, "reference_required": "reference" in roles,
        "prompt_applied": "positive" in roles,
        "source_digest": hashlib.sha256((source_json.encode("utf-8") if source_json is not None else bounded_json(graph))).hexdigest()}


def analyze_source(source_json, input_mode="placeholders", *, retained_contract=None):
    if input_mode not in {"placeholders", "node_bindings"}:
        raise ImagePreparationError("comfy_input_mode_invalid")
    result = analyze_graph(strict_json(source_json), source_json=source_json)
    if retained_contract is not None:
        if retained_contract.legacy_output_node is not None:
            workflow=ComfyWorkflow(prompt=result["prompt"],bindings=retained_contract.bindings or {},
                output_node=retained_contract.legacy_output_node,reference_required=retained_contract.reference_required)
        elif input_mode == "node_bindings":
            workflow=BoundWorkflow(input_mode=input_mode,prompt=result["prompt"],bindings=retained_contract.bindings or {},
                **({"output":retained_contract.output} if retained_contract.output is not None else {}))
        else:
            workflow=PlaceholderWorkflow(input_mode=input_mode,prompt=result["prompt"],
                **({"output":retained_contract.output} if retained_contract.output is not None else {}))
        validate_app_workflow(workflow)
    return {**result, "input_mode": input_mode}


def required_roles(workflow):
    if isinstance(workflow, PlaceholderWorkflow):
        return set(analyze_graph(workflow.prompt)["used_roles"])
    return set(workflow.bindings)


def validate_app_workflow(workflow):
    validate_graph(workflow.prompt)
    if not isinstance(workflow, PlaceholderWorkflow):
        if not set(workflow.bindings) <= set(TOKENS.values()):
            raise ImagePreparationError("comfy_bindings_invalid")
        positions = set()
        for binding in workflow.bindings.values():
            location = (binding.node_id, binding.input_name)
            if location in positions:
                raise ImagePreparationError("comfy_binding_collision")
            positions.add(location)
            node = workflow.prompt.get(binding.node_id)
            if not node or binding.input_name not in node["inputs"]:
                raise ImagePreparationError("comfy_binding_missing")
        if isinstance(workflow, ComfyWorkflow) and workflow.reference_required != ("reference" in workflow.bindings):
            raise ImagePreparationError("comfy_reference_contract_invalid")
    output = output_policy(workflow)
    if output.get("node_id") is not None and output["node_id"] not in workflow.prompt:
        raise ImagePreparationError("comfy_output_invalid")


def select_comfy_workflow(options: ComfyOptions, *, has_reference: bool) -> WorkflowInput:
    workflow = options.workflow
    if workflow is None:
        raise ImagePreparationError("comfy_workflow_required")
    validate_app_workflow(workflow)
    if "reference" in required_roles(workflow) and not has_reference:
        workflow = options.text_workflow
    if workflow is None or ("reference" in required_roles(workflow) and not has_reference):
        raise ImagePreparationError("comfy_reference_or_text_path_required")
    validate_app_workflow(workflow)
    return workflow


def output_policy(workflow):
    return {"mode": "legacy_single", "node_id": workflow.output_node} if isinstance(workflow, ComfyWorkflow) else workflow.output.model_dump()


def prepare_values(options, workflow, *, positive=None, negative=None, execute=False):
    validate_app_workflow(workflow)
    roles = required_roles(workflow)
    values = {}
    for role in roles - {"reference"}:
        if role in {"positive", "negative"}:
            if execute:
                values[role] = positive if role == "positive" else negative or ""
            continue
        value = options.values.get(role)
        if value is None and not isinstance(workflow, PlaceholderWorkflow):
            binding = workflow.bindings[role]
            value = workflow.prompt[binding.node_id]["inputs"][binding.input_name]
        if role in INT_ROLES:
            valid = type(value) is int
        elif role in NUMBER_ROLES:
            valid = type(value) in {int, float} and math.isfinite(value)
        else:
            valid = isinstance(value, str)
        if not valid:
            raise ImagePreparationError("comfy_value_required")
        if role == "clip_skip" and options.options_schema_version == 2 and (options.clip_skip_value_mode or "skip_count") == "skip_count":
            if value <= 0:
                raise ImagePreparationError("comfy_clip_skip_count_invalid")
            value = -value
        if role == "seed" and value == -1 and execute:
            value = secrets.randbits(32)
        values[role] = value
    return values


def render_workflow(workflow, values):
    validate_app_workflow(workflow)
    roles = required_roles(workflow)
    if roles - set(values):
        raise ImagePreparationError("comfy_value_missing")
    for role in roles:
        value = values[role]
        if not (type(value) is int if role in INT_ROLES else type(value) in {int, float} and math.isfinite(value) if role in NUMBER_ROLES else isinstance(value, str)):
            raise ImagePreparationError("comfy_value_invalid")
    result = copy.deepcopy(workflow.prompt)
    if isinstance(workflow, PlaceholderWorkflow):
        for item in analyze_graph(workflow.prompt)["positions"]:
            location = result[item["node_id"]]["inputs"]
            path = [item["input_name"], *item["path"]]
            for part in path[:-1]:
                location = location[part]
            location[path[-1]] = values[item["role"]]
    else:
        for role, binding in workflow.bindings.items():
            result[binding.node_id]["inputs"][binding.input_name] = values[role]
    return result


def freeze_comfy_request(request, *, has_reference=None):
    if request.provider != "comfyui" or request.comfy_execution is not None:
        return request
    options = ComfyOptions.model_validate(request.options)
    partner_submission_target(options.base_url, options.partner_auth)
    workflow = select_comfy_workflow(options, has_reference=bool(request.reference.asset_id) if has_reference is None else has_reference)
    values = prepare_values(options, workflow, positive=request.positive, negative=request.negative, execute=True)
    clip_mode = options.clip_skip_value_mode or ("node_value" if options.options_schema_version is None else "skip_count")
    actual_clip = values.get("clip_skip")
    display_clip = -actual_clip if actual_clip is not None and clip_mode == "skip_count" else actual_clip
    execution = ComfyExecution(options.options_schema_version,
        "workflow" if workflow is options.workflow else "text_workflow",
        hashlib.sha256(bounded_json(workflow.prompt)).hexdigest(), options.base_url,
        "legacy_bindings" if isinstance(workflow, ComfyWorkflow) else workflow.input_mode,
        output_policy(workflow), values, values.get("seed"), display_clip, clip_mode, actual_clip)
    return replace(request, comfy_execution=execution)


def restore_generation_request(value):
    value = dict(value)
    value["reference"] = EffectiveReference(**value["reference"])
    if value.get("comfy_execution"):
        value["comfy_execution"] = ComfyExecution(**value["comfy_execution"])
    return GenerationRequest(**value)
