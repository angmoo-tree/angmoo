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
    assert payload["schema_version"] == 2
    assert payload["module_count"] > 0
    assert payload["edge_count"] > 0
    assert payload["external_import_count"] > 0
    assert all("path" in item for item in payload["modules"])
    assert generator.DEFAULT_OUTPUT.read_text(encoding="utf-8") == first


def test_architecture_inventory_resolves_imported_modules_and_relative_imports(
    tmp_path: Path,
) -> None:
    app = tmp_path / "backend/app"
    services = app / "services"
    domain = app / "domains/alpha"
    services.mkdir(parents=True)
    domain.mkdir(parents=True)
    (app / "__init__.py").write_text("", encoding="utf-8")
    (services / "__init__.py").write_text("", encoding="utf-8")
    (services / "task.py").write_text("VALUE = 1\n", encoding="utf-8")
    (domain.parent / "__init__.py").write_text("", encoding="utf-8")
    (domain / "__init__.py").write_text("", encoding="utf-8")
    (domain / "public.py").write_text("VALUE = 2\n", encoding="utf-8")
    (domain / "use_case.py").write_text(
        "from app.services import task\nfrom . import public\n",
        encoding="utf-8",
    )

    payload = generator.build_inventory(root=tmp_path)
    modules = {item["module"]: item for item in payload["modules"]}

    assert modules["app.domains.alpha.use_case"]["imports"] == [
        "app.domains.alpha.public",
        "app.services.task",
    ]
