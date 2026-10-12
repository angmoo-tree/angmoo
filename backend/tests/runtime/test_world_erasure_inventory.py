"""Cold migrations use SQL descriptors without reversing model ownership."""
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import MetaData, create_engine

from app.runtime.persistence.model_registration import register_models
from app.runtime.world_deletion.inventory import ErasureInventory


def test_incomplete_descriptor_set_fails_instead_of_omitting_erasure_scopes():
    with pytest.raises(ValueError, match="world_erasure_metadata_incomplete"):
        ErasureInventory(MetaData())


def test_cold_process_installs_migration_fences_from_existing_schema(tmp_path):
    database = tmp_path / "cold.sqlite3"
    engine = create_engine(f"sqlite+pysqlite:///{database.as_posix()}")
    register_models().create_all(engine)
    engine.dispose()
    code = '''
import sys
from sqlalchemy import create_engine
from app.models import Base
from app.runtime.world_deletion.inventory import ErasureInventory
from app.runtime.world_deletion.fences import install_fences
assert not Base.metadata.tables
engine = create_engine(sys.argv[1])
with engine.begin() as connection:
    inventory = ErasureInventory.for_connection(connection)
    assert set(inventory.rules).issubset(inventory.tables)
    install_fences(connection)
    names = set(connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger'").scalars())
    assert 'world_erasure_world_insert' in names
    assert 'world_erasure_world_update' in names
    assert 'world_erasure_slot_insert' in names
assert not Base.metadata.tables
engine.dispose()
'''
    result = subprocess.run([sys.executable, "-c", code, f"sqlite+pysqlite:///{database.as_posix()}"],
                            cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
