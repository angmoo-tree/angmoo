"""Pure constraints shared by settings admission and API serialization."""
from app.domains.media.generation_contracts import ImagePreparationError


def endpoint_parameters(provider, endpoint):
    source = endpoint.get("supported_parameters", {})
    if not isinstance(source, dict):
        raise ImagePreparationError("model_capabilities_unverified")
    if provider == "openrouter":
        return source
    result = {}
    for field, external in (("resolution", "resolutions"), ("aspect_ratio", "aspect_ratio")):
        if isinstance(source.get(external), list):
            result[field] = {"type": "enum", "values": source[external]}
    for field in ("quality", "background", "seed", "output_compression"):
        descriptor = source.get(field)
        if isinstance(descriptor, dict):
            result[field] = descriptor
    if source.get("max_input_images", 0):
        result["input_references"] = {"type": "range", "min": 0, "max": source["max_input_images"]}
    return result


def validate_api_options(provider, endpoint, options):
    descriptors = endpoint_parameters(provider, endpoint)
    for field, value in options.items():
        if value is None:
            continue
        spec = descriptors.get(field)
        if not isinstance(spec, dict):
            raise ImagePreparationError(f"option_unsupported:{field}")
        kind = spec.get("type")
        if kind == "enum" and value not in spec.get("values", []):
            raise ImagePreparationError(f"option_value_invalid:{field}")
        if kind == "range" and (not isinstance(value, int) or isinstance(value, bool) or not spec.get("min", 0) <= value <= spec.get("max", 0)):
            raise ImagePreparationError(f"option_value_invalid:{field}")
        # Some routes use boolean as a capability flag for a numeric seed,
        # rather than as the wire value's type. ApiImageOptions owns its type.
        if kind == "boolean" and field != "seed" and not isinstance(value, bool):
            raise ImagePreparationError(f"option_value_invalid:{field}")
        if kind not in {"enum", "range", "boolean"}:
            raise ImagePreparationError(f"option_descriptor_unknown:{field}")
    return {field: value for field, value in options.items() if value is not None}


def validate_reference_metadata(endpoint, *, width, height, byte_size, content_type):
    constraints = endpoint.get("input_reference_constraints") or {}
    if not isinstance(constraints, dict):
        raise ImagePreparationError("reference_constraints_unverified")
    route = constraints.get("route", constraints)
    if not isinstance(route, dict):
        raise ImagePreparationError("reference_constraints_unverified")
    if constraints.get("max_items", 1) < 1:
        raise ImagePreparationError("reference_not_supported")
    for name, value in (("width", width), ("height", height)):
        if value < route.get(f"min_{name}", 1) or value > route.get(f"max_{name}", 16384):
            raise ImagePreparationError(f"reference_{name}_invalid")
    if byte_size > route.get("max_bytes", 32 * 1024 * 1024):
        raise ImagePreparationError("reference_bytes_invalid")
    formats = route.get("formats")
    if formats is not None and content_type.removeprefix("image/") not in formats:
        raise ImagePreparationError("reference_format_invalid")
