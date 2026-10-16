"""Frozen runtime must carry the same reviewed mutation producers as fresh SQL."""
import json
from pathlib import Path
import shutil
from app.runtime.memory import vector_mutations
from app.runtime.persistence.model_registration import register_models


def test_catalog_protects_existing_columns_and_is_available_in_sidecar_layout(tmp_path, monkeypatch):
    entries = vector_mutations.catalog()
    metadata = register_models()
    assert len(entries) == len({entry["table"] for entry in entries})
    for entry in entries:
        assert entry["columns"]
        assert set(entry["columns"]) <= set(metadata.tables[entry["table"]].c.keys())
    source = Path(vector_mutations.__file__).with_suffix(".json")
    frozen = tmp_path / "app/runtime/memory/vector_mutations.py"
    frozen.parent.mkdir(parents=True)
    shutil.copyfile(source, frozen.with_suffix(".json"))
    monkeypatch.setattr(vector_mutations, "__file__", str(frozen))
    assert vector_mutations.catalog() == entries
    script = (Path(__file__).resolve().parents[3] / "desktop/scripts/build-sidecar.ps1").read_text(encoding="utf-8")
    assert "--add-data $vectorMutationData" in script
    assert "vector_mutations.json');app/runtime/memory" in script
