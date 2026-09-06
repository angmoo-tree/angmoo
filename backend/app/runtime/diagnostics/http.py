"""Configure the diagnostic reader without opening a database or starting work."""
from fastapi import FastAPI
from app.runtime.diagnostics.status_composition import create_runtime_status_reader

def configure_runtime_diagnostics(app: FastAPI) -> None:
    app.state.runtime_status_reader_factory = create_runtime_status_reader
