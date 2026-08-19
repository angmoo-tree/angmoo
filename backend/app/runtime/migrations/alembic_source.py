"""Deterministic reader for the current Alembic revision corpus."""

from __future__ import annotations

import ast
from hashlib import sha256
from pathlib import Path

from app.domains.runtime.ports.migration_source import MigrationRevision


def _literal_assignment(tree: ast.Module, name: str) -> str | None:
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == name for target in targets):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and (value.value is None or isinstance(value.value, str)):
            return value.value
    return None


class AlembicMigrationSource:
    def __init__(self, versions_path: Path) -> None:
        self._versions_path = versions_path.resolve()

    def revisions(self) -> tuple[MigrationRevision, ...]:
        revisions: list[MigrationRevision] = []
        for path in sorted(self._versions_path.glob("*.py")):
            raw = path.read_bytes()
            tree = ast.parse(raw.decode("utf-8"), filename=str(path))
            revision = _literal_assignment(tree, "revision")
            if not revision:
                continue
            revisions.append(
                MigrationRevision(
                    revision=revision,
                    down_revision=_literal_assignment(tree, "down_revision"),
                    path=path.name,
                    sha256=sha256(raw).hexdigest(),
                )
            )
        return tuple(revisions)


__all__ = ["AlembicMigrationSource"]
