import hashlib
import json
import pytest
from app.runtime.memory.sqlite_vec1 import SqliteMemoryVectorIndex, MemoryVectorProjectionError
from app.runtime.memory.vector_generations import VectorGenerations
from memory.test_sqlite_vec1 import index, document


def generations(root, index):
    return VectorGenerations(root, lambda path, generation: SqliteMemoryVectorIndex(path,
        extension_path=index._extension,
        extension_sha256=hashlib.sha256(index._extension.read_bytes()).hexdigest(), generation=generation))


def test_corruption_preserves_original_and_resumes_one_staging_generation(tmp_path, index):
    manager = generations(tmp_path / "generations-test", index)
    active, staging = manager.open()
    assert staging is None
    active.upsert((document(),))
    old_path = active.database_path
    old_path.write_bytes(b"deliberately corrupt disposable test projection")
    restarted = generations(manager.root, index)
    active, staging = restarted.open()
    assert active is None and staging is not None
    staging.upsert((document("registered-only"),))
    generation = staging.generation
    again = generations(manager.root, index)
    active, resumed = again.open()
    assert active is None and resumed.generation == generation
    assert resumed.identity("registered-only") is not None
    again.promote(resumed)
    assert old_path.read_bytes() == b"deliberately corrupt disposable test projection"
    current, pending = generations(manager.root, index).open()
    assert current.generation == generation and pending is None
    assert current.identity("registered-only") is not None
    assert current.identity("one") is None


def test_invalid_marker_never_guesses_a_generation(tmp_path, index):
    manager = generations(tmp_path / "marker-test", index)
    manager.open()
    value = json.loads(manager.marker.read_text())
    value["active"] = "../../canonical"
    manager.marker.write_text(json.dumps(value))
    with pytest.raises(MemoryVectorProjectionError, match="generation_invalid"):
        generations(manager.root, index).open()


def test_disk_full_during_promotion_keeps_durable_active_and_staging(tmp_path, index, monkeypatch):
    import errno
    import app.runtime.memory.vector_generations as module
    manager = generations(tmp_path / "failed-promotion", index)
    active, _ = manager.open()
    active.upsert((document("old"),))
    manager.state["staging"] = "g-" + "a"*32
    staging = manager._index(manager.state["staging"])
    staging.open()
    staging.upsert((document("new"),))
    manager._save()
    before = manager.marker.read_bytes()
    def disk_full(*args):
        raise OSError(errno.ENOSPC, "disposable test filesystem full")
    with monkeypatch.context() as patch:
        patch.setattr(module.os, "replace", disk_full)
        with pytest.raises(OSError):
            manager.promote(staging)
    assert manager.marker.read_bytes() == before
    reopened, resumed = generations(manager.root, index).open()
    assert reopened.identity("old") is not None
    assert resumed.identity("new") is not None
    assert reopened.generation != resumed.generation
