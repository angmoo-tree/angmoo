"""Only actual protected ASGI export moves may alter an import-string assertion."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "asgi_preservation", ROOT / "scripts/ci/check_refactor_preservation.py"
)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

OLD = "app.public_main:app"
NEW = "app.main:public_app"
OLD_PATH = "backend/app/public_main.py"
NEW_PATH = "backend/app/main.py"
ORIGINAL = "def create_app(): return FastAPI()\napp = create_app()\n"
CURRENT = (
    "from functools import partial\n"
    "def create_app(*, profile='full'): return FastAPI()\n"
    "create_public_app = partial(create_app, profile='public')\n"
    "app = create_app()\npublic_app = create_public_app()\n"
)


@pytest.fixture
def sources(tmp_path, monkeypatch):
    destination = tmp_path / NEW_PATH
    destination.parent.mkdir(parents=True)
    destination.write_text(CURRENT)
    monkeypatch.setattr(p, "git_bytes", lambda *args, **kwargs: ORIGINAL.encode())
    return tmp_path, [{"tracked_files": {OLD_PATH: "protected-blob"}}]


def test_exact_protected_asgi_move_resolves_to_the_same_factory(sources):
    root, snapshots = sources
    assert p.validated_asgi_moves(
        {OLD: NEW}, {OLD_PATH: NEW_PATH}, snapshots, root
    ) == {OLD: NEW}
    before = 'assert args == ("app.public_main:app",)'
    after = 'assert args == ("app.main:public_app",)'
    assert p.normalized_assertion(before, [], {OLD: NEW}) == p.normalized_assertion(
        after, [], {OLD: NEW}
    )


@pytest.mark.parametrize(
    "origin,target",
    [
        ("secret-value", NEW),
        ("app.unknown:app", NEW),
        ("app.public_main:missing", NEW),
        (OLD, "app.main:missing"),
        (OLD, "app.main:public_app()"),
        (OLD, "../main:public_app"),
    ],
)
def test_unknown_module_export_and_non_import_literals_are_rejected(
    sources, origin, target
):
    root, snapshots = sources
    with pytest.raises(ValueError):
        p.validated_asgi_moves({origin: target}, {OLD_PATH: NEW_PATH}, snapshots, root)


@pytest.mark.parametrize(
    "source",
    [
        "def other_factory(): return FastAPI()\npublic_app = other_factory()\n",
        "public_app = object()\n",
        CURRENT + "public_app = object()\n",
        "create_app = create_public_app\ncreate_public_app = create_app\npublic_app = create_public_app()\n",
    ],
)
def test_unrelated_missing_duplicate_or_cyclic_factory_is_rejected(sources, source):
    root, snapshots = sources
    (root / NEW_PATH).write_text(source)
    with pytest.raises(ValueError):
        p.validated_asgi_moves({OLD: NEW}, {OLD_PATH: NEW_PATH}, snapshots, root)


def test_unprotected_origin_or_source_owner_mismatch_is_rejected(sources):
    root, snapshots = sources
    with pytest.raises(ValueError, match="protected Python source"):
        p.validated_asgi_moves({OLD: NEW}, {}, snapshots, root)
    with pytest.raises(ValueError, match="protected Python source"):
        p.validated_asgi_moves({OLD: NEW}, {OLD_PATH: NEW_PATH}, [], root)


def test_qualified_path_does_not_replace_other_strings_or_behavior_assertions(sources):
    root, snapshots = sources
    accepted = p.validated_asgi_moves({OLD: NEW}, {OLD_PATH: NEW_PATH}, snapshots, root)
    assert p.normalized_assertion(
        'assert text == "prefix app.public_main:app"', [], accepted
    ) != p.normalized_assertion(
        'assert text == "prefix app.main:public_app"', [], accepted
    )
    file_literals = p.path_literals({OLD_PATH: NEW_PATH})
    assert p.normalized_assertion(
        'assert text == "prefix app.public_main:app"', file_literals, accepted
    ) == p.normalized_assertion(
        'assert text == "prefix app.main:app"', [], accepted
    )
    assert p.normalized_assertion(
        'assert text == "prefix app.public_main:app"', file_literals, accepted
    ) != p.normalized_assertion(
        'assert text == "prefix app.main:public_app"', file_literals, accepted
    )
    test_path = root / "backend/tests/test_server.py"
    test_path.parent.mkdir()
    original = 'def test_server():\n assert args == ("app.public_main:app",)\n assert status == 503\n'
    snapshot = {
        "test_nodes": ["tests/test_server.py::test_server"],
        "test_assertions": {"tests/test_server.py": p.assertion_contracts(original)},
    }
    targets = {snapshot["test_nodes"][0]: snapshot["test_nodes"][0]}
    test_path.write_text(original.replace(OLD, NEW))
    assert p.check_assertions([snapshot], targets, {}, root, asgi_moves=accepted) == []
    test_path.write_text(original.replace(OLD, NEW).replace("503", "200"))
    assert any(
        "expectation missing or changed" in error
        for error in p.check_assertions(
            [snapshot], targets, {}, root, asgi_moves=accepted
        )
    )


def test_same_factory_wrong_profile_does_not_pass_frozen_api_contract(sources):
    root, snapshots = sources
    accepted = p.validated_asgi_moves(
        {OLD: "app.main:app"}, {OLD_PATH: NEW_PATH}, snapshots, root
    )
    frozen = [{"contracts": {"public": {"health": "runtime"}}}]
    assert p.asgi_contract_errors(
        accepted, {"asgi:" + OLD: {"health": "basic"}}, frozen
    )
    assert (
        p.asgi_contract_errors(accepted, {"asgi:" + OLD: {"health": "runtime"}}, frozen)
        == []
    )
