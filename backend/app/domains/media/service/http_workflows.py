"""Preserve raw Comfy JSON validation before framework decoding loses keys."""
import json
from fastapi import HTTPException, Request
from .comfy_workflows import strict_json
from ..generation_contracts import ImagePreparationError


async def require_comfy_raw_json(request: Request):
    raw = await request.body()
    comfy, duplicate, constant = False, False, False
    def pairs(items):
        nonlocal comfy, duplicate
        result = {}
        for name, value in items:
            duplicate = duplicate or name in result
            comfy = comfy or (name == "provider" and value == "comfyui") or (name == "input_mode" and value in ("placeholders", "node_bindings")) or name.startswith("comfyui:")
            result[name] = value
        return result
    def invalid_constant(value):
        nonlocal constant
        constant = True
        return value
    try:
        json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (ValueError, RecursionError, UnicodeError):
        return  # The ordinary request parser owns non-Comfy syntax errors.
    if comfy:
        try:
            if duplicate:
                raise ImagePreparationError("comfy_json_duplicate_key")
            if constant:
                raise ImagePreparationError("comfy_json_invalid")
            strict_json(raw.decode("utf-8"), limit=4 * 1024 * 1024)
        except (ImagePreparationError, UnicodeError) as exc:
            raise HTTPException(422, detail=str(exc) if isinstance(exc, ImagePreparationError) else "comfy_json_invalid") from None
