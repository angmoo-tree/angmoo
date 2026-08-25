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
    def __init__(
        self, versions_path: Path, *, head_revision: str | None = None
    ) -> None:
        self._versions_path = versions_path.resolve()
        self._head_revision = head_revision

    def revisions(self) -> tuple[MigrationRevision, ...]:
        revisions: list[MigrationRevision] = []
        for path in sorted(self._versions_path.glob("*.py")):
            raw = path.read_bytes()
            # Git may materialize the same migration as CRLF on Windows and LF
            # on Linux. Lineage identity is based on canonical source content,
            # not on the checkout's line-ending policy.
            canonical = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            tree = ast.parse(raw.decode("utf-8"), filename=str(path))
            revision = _literal_assignment(tree, "revision")
            if not revision:
                continue
            revisions.append(
                MigrationRevision(
                    revision=revision,
                    down_revision=_literal_assignment(tree, "down_revision"),
                    path=path.name,
                    sha256=sha256(canonical).hexdigest(),
                )
            )
        if self._head_revision is None:
            return tuple(revisions)

        by_revision = {item.revision: item for item in revisions}
        selected: set[str] = set()
        current: str | None = self._head_revision
        while current is not None:
            if current in selected or current not in by_revision:
                raise ValueError("frozen Alembic head is absent or cyclic")
            selected.add(current)
            current = by_revision[current].down_revision
        return tuple(item for item in revisions if item.revision in selected)


__all__ = ["AlembicMigrationSource"]
