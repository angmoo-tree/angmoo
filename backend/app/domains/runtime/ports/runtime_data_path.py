"""Stable ownership boundary for local runtime data paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class RuntimeDataPaths:
    root: Path
    canonical: Path
    graph: Path
    search: Path
    media: Path
    secrets: Path


@runtime_checkable
class RuntimeDataPathPort(Protocol):
    def resolve(self) -> RuntimeDataPaths: ...


__all__ = ["RuntimeDataPathPort", "RuntimeDataPaths"]
