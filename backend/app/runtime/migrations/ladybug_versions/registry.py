"""Immutable LadybugDB manifests and target-version replay builders."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from app.integrations.ladybug_projection import (
    LADYBUG_PROJECTION_SCHEMA_VERSION,
    ladybug_projection_contract,
)
from app.runtime.migrations.ladybug_versions.rebuild import (
    rebuild_projection_v1,
    rebuild_projection_v2,
)


GraphRebuild = Callable[..., dict[str, dict[str, list[str]]]]
GRAPH_REBUILDS: dict[int, GraphRebuild] = {
    1: rebuild_projection_v1,
    2: rebuild_projection_v2,
}
_MANIFEST_ROOT = Path(__file__).with_name("manifests")


class LadybugVersionContractError(RuntimeError):
    """Stable failure for projection contract drift or a missing builder."""


@dataclass(frozen=True)
class LadybugVersionManifest:
    projection_schema_version: int
    schema_digest: str
    projection_command_digest: str
    typed_query_digest: str
    parity_contract_version: int
    minimum_ladybug_version: str

    @property
    def manifest_sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.as_dict(),
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "projection_schema_version": self.projection_schema_version,
            "schema_digest": self.schema_digest,
            "projection_command_digest": self.projection_command_digest,
            "typed_query_digest": self.typed_query_digest,
            "parity_contract_version": self.parity_contract_version,
            "minimum_ladybug_version": self.minimum_ladybug_version,
        }


def load_ladybug_manifest(version: int) -> LadybugVersionManifest:
    path = _MANIFEST_ROOT / f"v{version}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        manifest = LadybugVersionManifest(
            projection_schema_version=int(payload["projection_schema_version"]),
            schema_digest=str(payload["schema_digest"]),
            projection_command_digest=str(payload["projection_command_digest"]),
            typed_query_digest=str(payload["typed_query_digest"]),
            parity_contract_version=int(payload["parity_contract_version"]),
            minimum_ladybug_version=str(payload["minimum_ladybug_version"]),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise LadybugVersionContractError(
            "ladybug_schema_manifest_missing"
        ) from exc
    if manifest.projection_schema_version != version:
        raise LadybugVersionContractError("ladybug_schema_manifest_mismatch")
    return manifest


def validate_latest_ladybug_contract() -> LadybugVersionManifest:
    manifest = load_ladybug_manifest(LADYBUG_PROJECTION_SCHEMA_VERSION)
    if manifest.as_dict() != ladybug_projection_contract():
        raise LadybugVersionContractError("ladybug_schema_manifest_mismatch")
    if LADYBUG_PROJECTION_SCHEMA_VERSION not in GRAPH_REBUILDS:
        raise LadybugVersionContractError(
            f"ladybug_rebuild_target_missing:v{LADYBUG_PROJECTION_SCHEMA_VERSION}"
        )
    return manifest


def rebuild_for_version(version: int) -> GraphRebuild:
    builder = GRAPH_REBUILDS.get(version)
    if builder is None:
        raise LadybugVersionContractError(
            f"ladybug_rebuild_target_missing:v{version}"
        )
    load_ladybug_manifest(version)
    return builder


__all__ = [
    "GRAPH_REBUILDS",
    "LadybugVersionContractError",
    "LadybugVersionManifest",
    "load_ladybug_manifest",
    "rebuild_for_version",
    "validate_latest_ladybug_contract",
]
