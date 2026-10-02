"""Optional writer auxiliary output, independently validated from the SNS post."""
from copy import deepcopy

IMAGE_INSTRUCTIONS = (
    "\nAlso return image_prompt: one English visual scene for this final SNS post. "
    "Describe observable action, setting, framing and objects. Do not output model settings, "
    "negative prompts or character identity extraction. Use an empty string when no scene is appropriate."
)


def with_image_schema(schema, enabled):
    if not enabled:
        return schema
    result = deepcopy(schema)
    result["properties"]["image_prompt"] = {"type": "string", "maxLength": 1800}
    result.setdefault("required", []).append("image_prompt")
    return result


def extract_scene(payload, enabled):
    value = dict(payload)
    scene = value.pop("image_prompt", "") if enabled else ""
    if not enabled:
        return value, "", None
    if not isinstance(scene, str) or len(scene) > 1800:
        return value, "", "scene_invalid"
    return value, scene.strip(), None
