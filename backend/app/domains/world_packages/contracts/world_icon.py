"""Required package extension: readers must preserve the World icon reference."""
import re

WORLD_ICON_EXTENSION = "angmoo.world-icon.v1"


def world_icon_reference(world) -> str | None:
    value = world.extensions.get(WORLD_ICON_EXTENSION)
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"asset_ref"}:
        raise ValueError("invalid_world_icon_extension")
    reference = value["asset_ref"]
    if not isinstance(reference, str) or not re.fullmatch(r"assets/sha256-[0-9a-f]{64}\.webp", reference):
        raise ValueError("invalid_world_icon_reference")
    return reference
