"""Portable reference and profile projection rules; no DB or filesystem IO."""
import re
import unicodedata
from app.domains.world_packages.exceptions import WorldPackageContractError, WorldPackageReasonCode

_REF_SEPARATORS = re.compile(r"[^a-z0-9-]+")


def _portable_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    text = _REF_SEPARATORS.sub("-", text.casefold().replace("_", "-"))
    return text.strip("-")[:64]


def _portable_map(values: list[str], *, label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    seen: set[str] = set()
    for value in values:
        portable = _portable_key(value)
        if not portable or portable in seen:
            raise WorldPackageContractError(WorldPackageReasonCode.REFERENCE_INVALID)
        seen.add(portable)
        result[value] = f"{label}/{portable}"
    return result


def _text_list(value: str, *, separator: str) -> list[str]:
    return [item.strip() for item in value.split(separator) if item.strip()]


def _portable_local_profile(value: object) -> dict[str, object]:
    source = value if isinstance(value, dict) else {}
    role_description = source.get("role_description")
    background = source.get("background")
    access_scope = source.get("access_scope")
    return {
        "role_description": role_description if isinstance(role_description, str) else "",
        "background": background if isinstance(background, str) else "",
        "access_scope": sorted(
            {
                item.strip()
                for item in access_scope
                if isinstance(item, str) and item.strip()
            }
        )[:30]
        if isinstance(access_scope, list)
        else [],
    }

