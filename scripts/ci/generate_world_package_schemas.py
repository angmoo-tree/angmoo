#!/usr/bin/env python3
"""Render the checked-in World Package v1 JSON Schema contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import TypeAlias


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from pydantic import BaseModel  # noqa: E402

from app.domains.world_packages.schemas.content import (  # noqa: E402
    AssetIndexDocument,
    CharactersDocument,
    PortableWorldDefinition,
    WorldCharactersDocument,
)
from app.domains.world_packages.schemas.manifest import (  # noqa: E402
    WorldPackageManifest,
)
from app.domains.world_packages.schemas.content_v2 import CharactersDocumentV2
from app.domains.world_packages.schemas.manifest_v2 import WorldPackageManifestV2


SchemaModel: TypeAlias = type[BaseModel]
OUTPUT_ROOT = (
    BACKEND_ROOT / "app" / "domains" / "world_packages" / "schemas" / "v1"
)
MODELS: tuple[tuple[str, SchemaModel], ...] = (
    ("manifest.schema.json", WorldPackageManifest),
    ("world.schema.json", PortableWorldDefinition),
    ("characters.schema.json", CharactersDocument),
    ("world-characters.schema.json", WorldCharactersDocument),
    ("assets-index.schema.json", AssetIndexDocument),
)


def render(model: SchemaModel, filename: str) -> str:
    schema = model.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://angmoo.dev/schemas/world-package/v1/{filename}"
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def expected_outputs(*, include_v2: bool = False) -> dict[Path, str]:
    outputs = {OUTPUT_ROOT / name: render(model, name) for name, model in MODELS}
    if not include_v2:
        return outputs
    for name, model in (("manifest.schema.json", WorldPackageManifestV2), ("characters.schema.json", CharactersDocumentV2)):
        outputs[OUTPUT_ROOT.parent / "v2" / name] = render(model, name).replace(
            "https://angmoo.dev/schemas/world-package/v1/", "https://angmoo.dev/schemas/world-package/v2/"
        )
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when checked-in schemas differ from the Pydantic contract",
    )
    args = parser.parse_args()

    stale: list[str] = []
    for path, payload in expected_outputs(include_v2=True).items():
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != payload:
                stale.append(path.relative_to(REPO_ROOT).as_posix())
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8", newline="\n")

    if stale:
        print("World Package schemas are stale:")
        for path in stale:
            print(f"- {path}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
