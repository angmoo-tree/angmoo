import json
import subprocess
import sys


def test_spawn_entry_and_progress_do_not_import_application_graph():
    code = """
import json, sys
from app.runtime.memory.search_worker_child import run_worker
from app.runtime.memory.search_worker_progress import ProgressSlots
blocked = [key for key in sys.modules if key.startswith((
    'pydantic', 'sqlalchemy', 'google', 'app.domains', 'app.contracts.core_experience',
    'app.runtime.memory.vector_worker', 'app.runtime.memory.sqlite_vec1'))]
print(json.dumps(blocked))
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert json.loads(result.stdout) == []


def test_fts_search_implementation_does_not_import_vector_or_fixture_graph():
    code = """
import json, sys
from app.runtime.memory.fts_search_child import search
print(json.dumps([key for key in sys.modules if key in (
    'app.runtime.memory.vector_worker', 'app.runtime.memory.sqlite_vec1',
    'app.contracts.core_experience')]))
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert json.loads(result.stdout) == []
