"""RoutinePost composition keeps the original cold ORM registration boundary."""

import os
from pathlib import Path
import subprocess
import sys


def test_routine_post_import_registers_the_same_models_without_opening_database():
    backend = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-c", """
import sys
from app.models import Base
import app.database as database
assert len(Base.metadata.tables) == 0
assert database._default_engine is None
from app.runtime.routine_posts import sqlalchemy_runtime
from sqlalchemy.orm import configure_mappers
configure_mappers()
assert len(Base.metadata.tables) == len(Base.registry.mappers) == 103
assert all(mapper.class_.metadata is Base.metadata for mapper in Base.registry.mappers)
assert database._default_engine is None
assert database._default_session_factory is None
assert 'app.compatibility.routine_posts.legacy' not in sys.modules
assert 'app.main' not in sys.modules
"""],
        cwd=backend,
        env={**os.environ, "APP_ENV": "test", "PYTHONPATH": str(backend)},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
