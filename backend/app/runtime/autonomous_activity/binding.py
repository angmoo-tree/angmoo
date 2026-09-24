"""Composition-owned dependencies; no second search runtime or credential store."""
from dataclasses import dataclass
from pathlib import Path
import logging
from threading import RLock
from typing import Any


@dataclass(frozen=True)
class ActivityRuntimeBinding:
    hybrid_service: Any
    data_directory: Path


logger = logging.getLogger(__name__)
_lock = RLock()
_binding: ActivityRuntimeBinding | None = None
_observer = None


def register(binding):
    global _binding, _observer
    with _lock:
        if _observer is not None:
            if not _observer.close():
                _binding = binding
                _observer = None
                logger.error('sns_observation_rebind_degraded_writer_still_running')
                return
        from app.runtime.diagnostics.sns_observation import SNSObserver

        _binding = binding
        try:
            _observer = SNSObserver(binding.data_directory)
        except Exception:
            _observer = None
            logger.exception('sns_observation_start_failed')


def current():
    with _lock:
        return _binding


def observer():
    with _lock:
        return _observer


def unregister(binding):
    global _binding, _observer
    with _lock:
        if _binding is binding:
            if _observer is not None:
                _observer.close()
            _observer = None
            _binding = None
