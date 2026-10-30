"""A frozen startup must read all reviewed erasure policies at their owned paths."""
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

from app.runtime.persistence import world_erasure_inventory as inventory
from app.runtime.persistence.model_registration import register_models

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"


def builder():
    spec = importlib.util.spec_from_file_location("world_erasure_build_resources",
        ROOT / "desktop/scripts/sidecar-world-erasure-resources.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_both_sidecar_layouts_receive_every_runtime_owner_at_its_exact_bundle_path(tmp_path, monkeypatch):
    arguments = builder().resource_arguments(BACKEND)
    assert arguments[::2] == ["--add-data"] * len(inventory.OWNERS)
    assert len(arguments) == 2 * len(inventory.OWNERS)
    bundled_module = tmp_path / "app/runtime/persistence/world_erasure_inventory.py"
    bundled_module.parent.mkdir(parents=True)
    monkeypatch.setattr(inventory, "__file__", str(bundled_module))
    metadata = register_models()
    # Reproduce the first frozen startup failure without launching any runtime.
    with pytest.raises(FileNotFoundError):
        inventory.ErasureInventory(metadata)
    rules = {}
    for owner, argument in zip(inventory.OWNERS, arguments[1::2], strict=True):
        source, target = argument.split(";", 1)
        assert Path(source) == BACKEND / f"app/domains/{owner}/repository/world_erasure.json"
        assert target == f"app/domains/{owner}/repository"
        destination = tmp_path / target / "world_erasure.json"
        destination.parent.mkdir(parents=True)
        shutil.copyfile(source, destination)
        assert destination.read_bytes() == Path(source).read_bytes()
        rules.update(json.loads(destination.read_text(encoding="utf-8"))["tables"])
    assert inventory.ErasureInventory(metadata).rules == rules
    script = (ROOT / "desktop/scripts/build-sidecar.ps1").read_text(encoding="utf-8")
    assert "@worldErasureArguments" in script
    assert script.index("@worldErasureArguments") > script.index("-m PyInstaller")


@pytest.mark.parametrize("mutation", ["missing", "wrong_owner", "wrong_version"])
def test_missing_or_unreviewed_policy_cannot_silently_disappear_from_the_package(tmp_path, mutation):
    module = tmp_path / "app/runtime/persistence/world_erasure_inventory.py"
    module.parent.mkdir(parents=True)
    module.write_text("OWNERS = ('worlds',)\n", encoding="utf-8")
    policy = tmp_path / "app/domains/worlds/repository/world_erasure.json"
    policy.parent.mkdir(parents=True)
    if mutation != "missing":
        policy.write_text(json.dumps({"owner":"chat" if mutation == "wrong_owner" else "worlds",
            "version":2 if mutation == "wrong_version" else 1,"tables":{}}), encoding="utf-8")
    with pytest.raises(FileNotFoundError if mutation == "missing" else ValueError):
        builder().resource_arguments(tmp_path)
