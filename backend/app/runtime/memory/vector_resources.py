"""Resolve only packaged, build-attested native extension resources."""
import json
import os
from pathlib import Path

from app.runtime.memory.sqlite_vec1 import MemoryVectorProjectionError, SqliteMemoryVectorIndex


def bundled_vector_index(database_path: Path, *, generation="v1"):
    directory = Path(__file__).resolve().parents[1] / "resources" / "vec1"
    try:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        expected_name = "vec1.dll" if os.name == "nt" else "vec1.so"
        if manifest["filename"] != expected_name or manifest["version"] != "0.7" or manifest["source_sha256"] != "8571bb4f77f9547d11ad11e2f72e0de7d3b2ab44e7930151998bce9377ed4b86":
            raise ValueError("resource_mismatch")
        return SqliteMemoryVectorIndex(database_path, extension_path=directory / expected_name,
                                       extension_sha256=manifest["sha256"], generation=generation)
    except (OSError, ValueError, KeyError):
        raise MemoryVectorProjectionError("memory_vector_resources_unavailable") from None
