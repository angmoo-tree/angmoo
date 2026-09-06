"""Retire the G06 facade only with its real profiles and cold behavior intact."""
import importlib.util
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "public_retirement_preservation", ROOT / "scripts/ci/check_refactor_preservation.py"
)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
r = p.public_factory_retirement
# Signed G5 source retains the G06 facade and actual lazy database names.
SOURCE = "924a8361867bd0228943082227221d78507f9027"


@pytest.fixture(scope="module")
def original():
    return {path: subprocess.check_output(
        ["git", "show", f"{SOURCE}:{path}"], cwd=ROOT
    ).decode("utf-8-sig") for path in (r.OLD, r.MAIN, r.TEST)}


@pytest.fixture
def candidate(tmp_path, original):
    for path in (r.MAIN, r.TEST):
        destination = tmp_path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((ROOT / path).read_text(encoding="utf-8"), encoding="utf-8")
    # Actual additions retain old files at #263; they do not replace their
    # blobs with the later G5 whole-tree source used by a synthetic fixture.
    import json
    snapshots = [json.loads((ROOT / "security/refactor_backend_checkpoint.json").read_text(encoding="utf-8"))]
    return tmp_path, snapshots, lambda *args, **kwargs: subprocess.check_output(["git", *args], cwd=ROOT)


def proof(candidate):
    root, snapshots, read_blob = candidate
    return r.validate(True, {r.OLD: r.MAIN}, snapshots, root, read_blob)


def test_frozen_facade_actual_profiles_and_cold_source_are_proven(candidate, original, monkeypatch):
    accepted = proof(candidate)
    assert accepted["exports"] == r.PUBLIC_BINDINGS
    assert accepted["frozen_facade"] == original[r.OLD]
    root, snapshots, read_blob = candidate
    monkeypatch.setattr(p, "git_bytes", read_blob)
    assert p.validated_asgi_moves(
        {"app.public_main:app": "app.main:public_app"}, {r.OLD: r.MAIN},
        snapshots, root, public_retirement=accepted,
    ) == {"app.public_main:app": "app.main:public_app"}
    with pytest.raises(ValueError, match="public profile"):
        p.validated_asgi_moves(
            {"app.public_main:app": "app.main:app"}, {r.OLD: r.MAIN},
            snapshots, root, public_retirement=accepted,
        )


@pytest.mark.parametrize("path", [r.OLD, "backend/app/public_main/__init__.py"])
def test_remaining_facade_file_or_package_is_rejected(candidate, path):
    root, _, _ = candidate
    destination = root / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="still exists"):
        proof(candidate)


@pytest.mark.parametrize("extra", [
    "\ndef create_app(): return object()\n", "\napp = object()\n",
    "\nfrom app.other import create_app\n", "\ndef __getattr__(name): return None\n",
    "\n__all__.append('extra')\n",
])
def test_original_facade_implementation_or_rebinding_is_not_retirable(original, extra):
    with pytest.raises(ValueError):
        r.facade_exports(original[r.OLD] + extra)


@pytest.mark.parametrize("before,after", [
    ('profile="public"', 'profile="full"'),
    ("component_manager_factory=lambda: None", "component_manager_factory=create_single_backend_runtime_components"),
    ('profile: Literal["full", "public"] = "full"', 'profile: Literal["full", "public"] = "public"'),
    ("public_app = create_public_app(", "public_app = create_app("),
    ("from functools import partial", "from custom import partial"),
])
def test_actual_factory_defaults_partial_and_export_cannot_change(original, before, after):
    source = (ROOT / r.MAIN).read_text(encoding="utf-8")
    assert before in source
    with pytest.raises(ValueError):
        r.validate_main(source.replace(before, after), original[r.MAIN])


@pytest.mark.parametrize("extra", [
    "\npublic_app = app\n", "\nfrom custom import create_public_app\n",
    "\ndef create_app(): return FastAPI()\n", "\nclass partial: pass\n",
])
def test_factory_bindings_must_be_unique(original, extra):
    with pytest.raises(ValueError):
        r.validate_main((ROOT / r.MAIN).read_text(encoding="utf-8") + extra, original[r.MAIN])


@pytest.mark.parametrize("before,after", [
    ("assert main.app is not main.public_app", "assert main.app is main.public_app"),
    ("assert not root.exists()", "assert True"),
    ("raise ImportError('no bundled PostgreSQL DBAPI')", "pass"),
    ("main.create_app()\nassert all", "assert all"),
    ("timeout=30", "timeout=300"),
    ('[sys.executable, "-c", source,', '[sys.executable, "-c", "pass",'),
    ('    backend = Path(__file__)', '    source = "pass"\n    backend = Path(__file__)'),
    ("from pathlib import Path", "from custom import Path"),
    ("import subprocess", "import subprocess\nsubprocess = object()"),
    ('    assert main.create_public_app.func is main.create_app', '    assert main.create_public_app is main.create_public_app'),
    ('    assert calls == ["construct", "start", "stop"]', '    assert calls == []'),
])
def test_cold_process_connection_and_original_behavior_are_preserved(original, before, after):
    current = (ROOT / r.TEST).read_text(encoding="utf-8")
    assert before in current
    with pytest.raises(ValueError):
        r.validate_tests(original[r.TEST], current.replace(before, after))


@pytest.mark.parametrize("extra", [
    "\nmain = object()\n", "\nfrom custom import Path\n",
    "\ndef main(): pass\n", "\nfrom app.main import *\n",
])
def test_shadowed_test_imports_are_not_rebound(original, extra):
    with pytest.raises(ValueError):
        r.validate_tests(original[r.TEST] + extra, (ROOT / r.TEST).read_text(encoding="utf-8"))


def test_partial_identity_bundle_and_unrelated_identity_are_not_retired(original):
    current = (ROOT / r.TEST).read_text(encoding="utf-8")
    before = original[r.TEST]
    with pytest.raises(ValueError, match="five-identity"):
        r.validate_tests(before.replace("    assert public_main.create_app is main.create_public_app\n", ""), current)
    with pytest.raises(ValueError):
        r.validate_tests(before.replace("assert main.create_public_app.func is main.create_app", "assert extra is actual"), current)


@pytest.mark.parametrize("source", [
    "import app.public_main\n", "from app import public_main\n",
    "from app.public_main import create_app\n", "from app.public_main.extra import factory\n", "from .public_main import create_app\n",
    "from . import public_main\n", "import importlib\nimportlib.import_module('app.public_main')\n",
    "import importlib\nimportlib.import_module('app.' + 'public_main')\n",
    "import importlib\nimportlib.import_module('app.' + name)\n",
    "import importlib\nmodule = 'app.public_main'\nimportlib.import_module(module)\n",
])
def test_static_and_unresolved_retired_dynamic_consumers_are_rejected(candidate, source):
    root, _, _ = candidate
    (root / "backend/app/consumer.py").write_text(source, encoding="utf-8")
    with pytest.raises(ValueError, match="consumer"):
        proof(candidate)


def test_historical_strings_are_distinct_from_actual_imports(candidate):
    root, _, _ = candidate
    (root / "backend/app/consumer.py").write_text(
        "from app.main import public_app\nlogger_name='app.public_main'\n", encoding="utf-8"
    )
    assert proof(candidate)["exports"]["app"] == "public_app"


def test_exact_bundle_counter_keeps_unrelated_assertions(candidate, original):
    accepted = proof(candidate)
    functions = p.assertion_contracts(original[r.TEST])
    fragments = r.required_fragments(functions[r.BUNDLE_TEST], original[r.TEST], r.BUNDLE_TEST, accepted)
    assert len(fragments) == len(functions[r.BUNDLE_TEST]) - 1
    assert r.ABSENT in fragments
    assert "assert main.create_public_app.func is main.create_app" in fragments
    assert not any("public_main" in f for f in fragments if f != r.ABSENT)


def test_backend_script_is_an_active_consumer(candidate):
    root, _, _ = candidate
    target = root / 'backend/scripts/migrate.py'
    target.parent.mkdir(parents=True)
    target.write_text('from app import public_main\n', encoding='utf-8')
    with pytest.raises(ValueError, match='consumer'):
        proof(candidate)


@pytest.mark.parametrize('failure', ['ancestor', 'signature', 'order', 'introduction', 'facade'])
def test_original_signed_provenance_is_required(candidate, failure):
    root, snapshots, read_blob = candidate
    def wrong(*args, **kwargs):
        if failure == 'ancestor' and args == ('merge-base', r.FACTORY_SOURCE, 'HEAD'):
            return b'wrong ancestor'
        if failure == 'signature' and args == ('show', '-s', '--format=%B', r.FACTORY_SOURCE):
            return b'unsigned source'
        if failure == 'order' and args == ('merge-base', r.FACADE_SOURCE, r.FACTORY_SOURCE):
            return b'wrong order'
        if failure == 'introduction' and args[0] == 'diff-tree':
            return b''
        if failure == 'facade' and args == ('show', r.FACTORY_SOURCE + ':' + r.OLD):
            return read_blob(*args, **kwargs) + b'\napp = object()\n'
        return read_blob(*args, **kwargs)
    with pytest.raises(ValueError):
        proof((root, snapshots, wrong))
