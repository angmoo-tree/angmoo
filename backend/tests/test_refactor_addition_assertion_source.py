"""Existing-file additions keep their own immutable source for path proofs."""
import pytest

from test_refactor_backend_checkpoint import p, snapshot, write


@pytest.mark.parametrize("altered", [False, True])
def test_existing_file_addition_reads_its_commit_and_preserves_predicate(monkeypatch, tmp_path, altered):
    source = (
        "from pathlib import Path\n"
        "APP_ROOT = Path(__file__).resolve().parents[1] / 'app'\n"
        "def test_contract():\n"
        "    root = APP_ROOT / 'domains' / 'world_packages'\n"
        "    assert (root / 'api' / 'routes.py').exists()\n"
    )
    old = "tests/test_old.py::test_contract"
    new = "tests/world_packages/test_new.py::test_contract"
    expected = snapshot(source, old)
    expected["commit"] = "a" * 40
    expected["tracked_files"] = {}
    reads = []

    def history(*args, **kwargs):
        reads.append(args)
        assert args == ("show", expected["commit"] + ":backend/tests/test_old.py")
        assert kwargs["root"] == tmp_path
        return source.encode()

    monkeypatch.setattr(p, "git_bytes", history)
    changed = source.replace("parents[1]", "parents[2]").replace("'api' / 'routes.py'", "'router.py'")
    if altered:
        changed = changed.replace(".exists()", ".is_file()")
    write(tmp_path, "backend/tests/world_packages/test_new.py", changed)
    files = {"backend/app/domains/world_packages/api/routes.py": "backend/app/domains/world_packages/router.py"}
    errors = p.check_assertions([expected], {old: new}, files, tmp_path)
    assert reads
    if altered:
        assert any("expectation missing or changed" in error for error in errors)
    else:
        assert errors == []
