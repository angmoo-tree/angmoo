"""Bind diagnostic/graph reader construction once per application."""
from fastapi import FastAPI
from app.runtime.graph_projection.diagnostic_references import SqlAlchemyDiagnosticReferences


def configure_relationships_runtime(app: FastAPI) -> None:
    app.state.relationships_read_references_factory = SqlAlchemyDiagnosticReferences
