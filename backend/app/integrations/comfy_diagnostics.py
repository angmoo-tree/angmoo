"""Bounded selected ComfyUI error fields, with execution-value redaction."""
import json
import re
from app.domains.media.schemas import ProviderDiagnostic


def diagnostic(payload, *, stage, kind="error", sensitive=(), truncated=False):
    def safe(value):
        nonlocal truncated
        if not isinstance(value, (str, int, float)):
            return None
        value = str(value)
        for secret in sorted((item for item in sensitive if isinstance(item, str) and item), key=len, reverse=True):
            value = value.replace(secret, "[redacted]")
        value = re.sub(r"(?:data:image/[^;]+;base64,)?[A-Za-z0-9+/]{128,}={0,2}", "[redacted]", value)
        if len(value) > 2048:
            value = value[:2048]
            truncated = True
        return value
    messages = []
    def add(raw, node_id=None):
        nonlocal truncated
        if not isinstance(raw, dict):
            return
        if len(messages) >= 20:
            truncated = True
            return
        item = {name: safe(raw.get(name)) for name in ("type", "message", "exception_type", "exception_message", "class_type", "input_name") if raw.get(name) is not None}
        if node_id is not None:
            item["node_id"] = safe(node_id)
        if item:
            messages.append(item)
    if isinstance(payload, dict):
        add(payload.get("error"))
        nodes = payload.get("node_errors", {})
        if isinstance(nodes, dict):
            for node_id, item in nodes.items():
                if isinstance(item, dict):
                    for error in item.get("errors", []) if isinstance(item.get("errors"), list) else []:
                        if isinstance(error, dict):
                            add({**error, "class_type": item.get("class_type")}, node_id)
        status = payload.get("status", {})
        if isinstance(status, dict):
            for message in status.get("messages", []) if isinstance(status.get("messages"), list) else []:
                if isinstance(message, list) and len(message) == 2 and message[0] == "execution_error" and isinstance(message[1], dict):
                    add(message[1], message[1].get("node_id"))
    if len(messages) > 20:
        messages = messages[:20]
        truncated = True
    result = {"kind": kind, "stage": stage, "messages": [], "truncated": truncated}
    for item in messages:
        result["messages"].append(item)
        if len(json.dumps(result, ensure_ascii=False).encode()) > 16 * 1024:
            result["messages"].pop()
            result["truncated"] = True
            break
    return ProviderDiagnostic.model_validate(result).model_dump(exclude_none=True)
