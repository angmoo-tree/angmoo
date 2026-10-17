"""Bounded numeric snapshots; no request context or content crosses the worker."""
from dataclasses import dataclass
from threading import Lock
from time import monotonic


@dataclass(frozen=True, slots=True)
class CanonicalPhaseReceipt:
    stage: str
    elapsed_ms: float
    sql_count: int
    completed: bool


@dataclass(frozen=True, slots=True)
class CanonicalReadReceipt:
    stage: str
    wait_ms: float | None
    elapsed_ms: float | None
    sql_count: int | None
    cleaned: bool | None
    unique_nodes: int | None
    memo_hits: int | None
    phases: tuple[CanonicalPhaseReceipt, ...] = ()
    metrics_complete: bool = True


class ReadProgress:
    def __init__(self, stage, submitted):
        self.lock, self.stage, self.submitted = Lock(), stage, submitted
        self.started = self.ended = None
        self.counters = (0, 0, None, None)
        self.phases, self.active = [], None

    def start(self):
        with self.lock:
            self.started = monotonic()

    def update(self, counters):
        with self.lock:
            self.counters = tuple(counters)

    def phase_start(self, name, sql_count):
        with self.lock:
            self.active = name, monotonic(), sql_count

    def phase_end(self, sql_count, completed):
        with self.lock:
            name, started, initial = self.active
            if len(self.phases) < 2:
                self.phases.append(CanonicalPhaseReceipt(name, (monotonic()-started)*1000, sql_count-initial, completed))
            self.active = None

    def finish(self, counters):
        with self.lock:
            self.counters, self.ended = tuple(counters), monotonic()

    def receipt(self):
        with self.lock:
            current = self.ended or monotonic()
            phases = list(self.phases)
            if self.active is not None and len(phases) < 2:
                name, started, initial = self.active
                phases.append(CanonicalPhaseReceipt(name, (current-started)*1000, self.counters[0]-initial, False))
            started = self.started
            return CanonicalReadReceipt(self.stage,
                None if started is None else (started-self.submitted)*1000,
                None if started is None else (current-started)*1000,
                None if started is None else self.counters[0],
                None if started is None else bool(self.counters[1]), self.counters[2], self.counters[3],
                tuple(phases), self.ended is not None)
