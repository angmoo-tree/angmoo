"""Composition-owned dependencies; no second search runtime or credential store."""
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any


@dataclass(frozen=True)
class ActivityRuntimeBinding:
    hybrid_service: Any
    data_directory: Path


_lock = RLock()
_binding: ActivityRuntimeBinding | None = None


def register(binding):
    global _binding
    with _lock:
        _binding = binding


def current():
    with _lock:
        return _binding


def unregister(binding):
    global _binding
    with _lock:
        if _binding is binding:
            _binding = None
