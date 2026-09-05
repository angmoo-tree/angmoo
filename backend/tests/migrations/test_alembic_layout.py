"""Keep the historical Alembic graph usable after its physical relocation."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest


ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
INI = BACKEND / "alembic.ini"
CHECKPOINT = ROOT / "security/refactor_backend_checkpoint.json"
OLD_PREFIX = "backend/app/alembic/versions/"


def test_historical_revision_blobs_and_graph_remain_unchanged():
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    historical = {
        path: digest
        for path, digest in checkpoint["tracked_files"].items()
        if path.startswith(OLD_PREFIX) and path.endswith(".py")
    }
    assert len(historical) == 88
    expected_graph = {}
    for old_path, expected_blob in historical.items():
        current_path = ROOT / old_path.replace("backend/app/alembic/", "backend/alembic/", 1)
        data = current_path.read_bytes().replace(b"\r\n", b"\n")
        actual_blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        assert actual_blob == expected_blob, old_path
        assignments = {}
        for node in ast.parse(data).body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id in {"revision", "down_revision"}:
                    assignments[node.target.id] = ast.literal_eval(node.value)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                        assignments[target.id] = ast.literal_eval(node.value)
        expected_graph[assignments["revision"]] = assignments["down_revision"]

    script = ScriptDirectory.from_config(Config(str(INI)))
    actual_graph = {revision.revision: revision.down_revision for revision in script.walk_revisions()}
    assert actual_graph == expected_graph
    assert len(actual_graph) == 88
    assert script.get_heads() == ["20260904_0089"]
    assert not list((BACKEND / "app/alembic").rglob("*.py"))


def test_alembic_heads_from_outside_backend(tmp_path):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(INI), "heads"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "20260904_0089 (head)"


def test_alembic_env_registers_canonical_metadata_on_real_memory_connection(tmp_path):
    # Exercise env.py and the SQLAlchemy connection without executing historical
    # PostgreSQL upgrade bodies against SQLite or touching an installed database.
    program = textwrap.dedent("""
        import json
        from pathlib import Path
        import sys
        from alembic.config import Config
        from alembic.runtime.environment import EnvironmentContext
        from alembic.script import ScriptDirectory
        from sqlalchemy import text

        backend = Path(sys.argv[1])
        checkpoint = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        expected_tables = set(checkpoint["contracts"]["orm_tables"])
        config = Config(str(backend / "alembic.ini"))
        script = ScriptDirectory.from_config(config)
        inspected = []

        def inspect_only(revisions, context):
            import app
            from app.core.db import Base
            assert Path(app.__file__).resolve() == (backend / "app/__init__.py").resolve()
            assert context.connection.dialect.name == "sqlite"
            assert context.connection.engine.url.database == ":memory:"
            assert context.connection.execute(text("SELECT 1")).scalar_one() == 1
            metadata = context.opts["target_metadata"]
            assert metadata is Base.metadata
            assert set(metadata.tables) == expected_tables
            assert revisions == ()
            inspected.append(len(metadata.tables))
            return []

        with EnvironmentContext(config, script, fn=inspect_only):
            script.run_env()
        assert len(inspected) == 1
        print(json.dumps({"registered_tables": inspected[0], "revision_bodies_run": 0}))
    """)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.update({"DATABASE_URL": "sqlite+pysqlite:///:memory:", "APP_ENV": "test"})
    result = subprocess.run(
        [sys.executable, "-c", program, str(BACKEND), str(CHECKPOINT)],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    result_data = json.loads(result.stdout)
    expected_count = len(json.loads(CHECKPOINT.read_text(encoding="utf-8"))["contracts"]["orm_tables"])
    assert result_data == {"registered_tables": expected_count, "revision_bodies_run": 0}
    assert not list(tmp_path.rglob("*.sqlite3"))


@pytest.mark.parametrize(
    ("generator", "revision"),
    [
        ("d_world_chat", "20260831_0084_world_scoped_chat_identity.py"),
        ("f_memory", "20260831_0085_canonical_memory_schema.py"),
        ("j_response_generation", "20260831_0086_chat_response_request_lifecycle.py"),
        ("p_evidence_response_streaming", "20260903_0087_world_chat_model_binding.py"),
        ("r_today_sns_activity", "20260904_0088_social_action_subjective_context.py"),
    ],
)
def test_historical_inventory_record_keeps_old_path_and_digest(generator, revision):
    filename = ROOT / f"scripts/ci/generate_p8_l_{generator}_inventory.py"
    spec = importlib.util.spec_from_file_location(f"g4_inventory_{generator}", filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    old_path = OLD_PREFIX + revision
    record = module._record(old_path)
    data = (BACKEND / "alembic/versions" / revision).read_bytes().replace(b"\r\n", b"\n")
    assert record == {
        "path": old_path,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
