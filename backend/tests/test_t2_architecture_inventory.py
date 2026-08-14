from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR_PATH = REPO_ROOT / "scripts/ci/generate_architecture_inventory.py"
SPEC = importlib.util.spec_from_file_location("angmoo_t2_architecture", GENERATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
generator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = generator
SPEC.loader.exec_module(generator)


def test_architecture_inventory_is_deterministic_and_current() -> None:
    first = generator.render()
    second = generator.render()
    payload = json.loads(first)

    assert first == second
    assert payload["module_count"] > 0
    assert payload["edge_count"] > 0
    assert generator.DEFAULT_OUTPUT.read_text(encoding="utf-8") == first
