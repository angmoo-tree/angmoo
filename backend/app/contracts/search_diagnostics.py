"""Bounded, content-free search traces. Never an execution or logging dependency."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Literal
import json

from pydantic import BaseModel, ConfigDict, Field

Count = Annotated[int, Field(strict=True, ge=0, le=1_000_000_000)]
Duration = Annotated[float, Field(ge=0, le=1_000_000_000, allow_inf_nan=False)]
Alias = Annotated[str, Field(pattern=r"^[dimsrek][0-9]{1,3}$", max_length=4)]
Code = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$", max_length=128)]
Axis = Literal["fts", "vector"]
StageName = Literal["embedding", "slot_wait", "process_start", "child_bootstrap",
    "extension_verify", "query_validate", "db_open", "extension_load", "metadata_read",
    "eligible_count", "nn_query", "mapping_read", "result_transport", "worker_cleanup", "fts_search"]
FailureCode = Literal["deadline_exceeded", "sqlite_busy", "sqlite_locked", "sqlite_error",
    "extension_integrity_failed", "extension_load_failed", "mapping_missing",
    "worker_start_failed", "worker_exited", "result_eof", "result_decode_failed",
    "invalid_query", "cancelled", "unknown_error"]


class SafeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SearchStage(SafeModel):
    axis: Axis
    stage: StageName
    clock_domain: Literal["parent", "child"]
    state: Literal["running", "completed", "failed", "cancelled", "unknown"]
    start_ms: Duration
    end_ms: Duration | None = None
    elapsed_ms: Duration | None = None
    budget_at_start_ms: Duration
    remaining_at_end_ms: Duration | None = None
    deadline_exceeded: bool = False


class SearchFailure(SafeModel):
    failure_code: FailureCode
    failure_stage: StageName | None = None
    exception_kind: Literal["TimeoutError", "OperationalError", "DatabaseError",
        "OSError", "MemoryVectorProjectionError", "EOFError", "ValueError", "Unknown"] = "Unknown"
    sqlite_error_code: Annotated[int, Field(strict=True, ge=0, le=65535)] | None = None


class SearchTerminal(SafeModel):
    axis: Axis
    axis_status: Literal["ready", "partial", "disabled", "unavailable", "cancelled"] | None = None
    terminal_state: Literal["success", "error", "deadline", "cancelled", "unexpected_exit", "disabled"]
    failure: SearchFailure | None = None
    last_observed_stage: StageName | None = None
    cause_certainty: Literal["reported", "observed_exit", "deadline_observed", "last_stage_only", "unknown"] = "unknown"
    worker_started: bool = False
    nn_query_started: bool | None = None
    result_received: bool = False
    terminal_observed: bool = False
    terminate_sent: bool = False
    kill_sent: bool = False
    joined: bool = False
    worker_exit_code: Annotated[int, Field(strict=True, ge=-(2**63), le=2**63-1)] | None = None
    termination_reason: Literal["none", "deadline", "caller_cancel", "result_received_cleanup", "abnormal_exit", "unknown"] = "none"
    cleanup_error_code: Literal["cleanup_failed"] | None = None
    eligible_vector_count: Count | None = None
    requested_generation: Code | None = None
    observed_generation: Code | None = None
    requested_profile: Code | None = None
    observed_schema_revision: Code | None = None
    generation_match: bool | None = None
    metadata_status: Literal["not_requested", "observed", "unavailable", "budget_skipped"] = "not_requested"
    stage_events_dropped: Count = 0


class SearchLineage(SafeModel):
    stage: Literal["axis", "rrf", "canonical", "select", "hydrate", "evidence",
        "dedup", "limit", "freeze", "crg", "inspector", "bundle"]
    action: Literal["returned", "accepted", "excluded", "merged", "selected",
        "added", "existing", "missing", "kept", "linked", "count"]
    axis: Axis | None = None
    document_ref: Alias | None = None
    identity_ref: Alias | None = None
    memory_ref: Alias | None = None
    source_ref: Alias | None = None
    record_ref: Alias | None = None
    evidence_ref: Alias | None = None
    key_ref: Alias | None = None
    related_ref: Alias | None = None
    rank: Count | None = None
    count: Count | None = None
    reason: Literal["identity", "memory_identity", "reference", "text",
        "validation", "scope", "version", "missing", "filter", "item_budget",
        "character_budget", "available", "degraded", "other"] | None = None


class SearchDiagnosticTrace(SafeModel):
    version: Literal["search-diagnostic-trace.v1"] = "search-diagnostic-trace.v1"
    coverage: Literal["complete", "partial"] = "complete"
    stages: tuple[SearchStage, ...] = Field(default=(), max_length=48)
    terminals: tuple[SearchTerminal, ...] = Field(default=(), max_length=2)
    lineage: tuple[SearchLineage, ...] = Field(default=(), max_length=160)
    stage_events_dropped: Count = 0
    lineage_edges_dropped: Count = 0
    aliases_dropped: Count = 0
    detail_rows_dropped: Count = 0


@dataclass
class SearchTraceCollector:
    stages: dict = field(default_factory=dict)
    terminals: dict = field(default_factory=dict)
    edges: list = field(default_factory=list)
    aliases: dict = field(default_factory=dict, repr=False)
    stage_dropped: int = 0
    edge_dropped: int = 0
    alias_dropped: int = 0

    def alias(self, kind, identity):
        if identity is None:
            return None
        key = (kind, identity)
        if key in self.aliases:
            return self.aliases[key]
        if kind not in "dimsrek" or len(self.aliases) >= 256:
            self.alias_dropped += 1
            return None
        value = f"{kind}{1 + sum(k[0] == kind for k in self.aliases)}"
        self.aliases[key] = value
        return value

    def add_stage(self, stage):
        key = (stage.axis, stage.clock_domain, stage.stage)
        old = self.stages.get(key)
        if old is not None and old.start_ms == stage.start_ms and old.end_ms is not None and stage.end_ms is None:
            return  # A terminal envelope can precede the last progress snapshot.
        if key not in self.stages and len(self.stages) >= 48:
            self.stage_dropped += 1
        else:
            self.stages[key] = stage

    def add_edge(self, edge):
        if len(self.edges) >= 160:
            # Final edges explain what reached the model; evict early rank rows.
            if edge.stage in {"evidence", "dedup", "limit", "freeze", "crg", "inspector", "bundle"}:
                index = next((i for i, row in enumerate(self.edges) if row.stage in {"axis", "rrf", "canonical"}), None)
                if index is not None:
                    self.edges.pop(index)
                    self.edges.append(edge)
            self.edge_dropped += 1
        else:
            self.edges.append(edge)

    def payload(self):
        dropped = self.stage_dropped + sum(t.stage_events_dropped for t in self.terminals.values())
        partial = dropped or self.edge_dropped or self.alias_dropped or any(
            t.terminal_state not in {"disabled"} and not t.terminal_observed for t in self.terminals.values())
        return SearchDiagnosticTrace(coverage="partial" if partial else "complete",
            stages=tuple(self.stages.values()), terminals=tuple(self.terminals.values()),
            lineage=tuple(self.edges), stage_events_dropped=dropped,
            lineage_edges_dropped=self.edge_dropped, aliases_dropped=self.alias_dropped).model_dump(mode="json")


def collector():
    # Import here avoids circular initialization and allocates nothing for OFF.
    from app.contracts.retrieval_observation import current
    observation = current.get()
    if observation is None or not observation.detailed:
        return None
    if observation.search_trace is None:
        observation.search_trace = SearchTraceCollector()
    return observation.search_trace


def lineage(stage, action, *, identities=None, **values):
    target = collector()
    if target is None:
        return
    try:
        refs = {}
        for name, (kind, identity) in (identities or {}).items():
            refs[name] = target.alias(kind, identity)
        target.add_edge(SearchLineage(stage=stage, action=action, **refs, **values))
    except Exception:
        target.edge_dropped += 1


def record_identity(record):
    """No domain imports: callers supply their already authorized record."""
    return {
        "memory_ref": ("m", record.memory_item_id),
        "record_ref": ("r", record.reference),
        "source_ref": ("s", (record.source_type.value if record.source_type is not None else record.kind.value, record.canonical_source_id)),
    }


def trace_payload():
    target = collector()
    return None if target is None else target.payload()


def evidence_identities(item):
    ids = {"evidence_ref": ("e", item.opaque_reference)}
    if item.locator is not None:
        ids["source_ref"] = ("s", (item.locator.source_type or item.locator.kind.value, item.locator.source_id))
    return ids


def evidence_lineage(stage, items):
    if collector() is not None:
        for rank, item in enumerate(items, 1):
            lineage(stage, "returned", rank=rank, identities=evidence_identities(item))


def bounded_capture(details, trace):
    """Reserve terminal data and clip in batches, avoiding quadratic JSON work."""
    trace = None if trace is None else SearchDiagnosticTrace.model_validate(trace).model_dump(mode="json")
    result = {"details": list(details[:24]), "search_trace": trace}
    def size(value):
        return len(json.dumps(value, ensure_ascii=True).encode())
    total = size(result)
    while total > 64 * 1024:
        excess = total - 64 * 1024
        low = [i for i, row in enumerate(trace["lineage"]) if row["stage"] in {"axis", "rrf", "canonical"}] if trace else []
        if low:
            removed, freed = set(), 0
            for i in low:
                removed.add(i)
                freed += size(trace["lineage"][i]) + 2
                if freed >= excess:
                    break
            trace["lineage"] = [row for i, row in enumerate(trace["lineage"]) if i not in removed]
            trace["lineage_edges_dropped"] += len(removed)
            trace["coverage"] = "partial"
        elif result["details"]:
            freed = count = 0
            while result["details"] and freed < excess:
                freed += size(result["details"].pop()) + 2
                count += 1
            if trace:
                trace["coverage"] = "partial"
                trace["detail_rows_dropped"] += count
        elif trace and trace["lineage"]:
            freed = count = 0
            while trace["lineage"] and freed < excess:
                freed += size(trace["lineage"].pop(0)) + 2
                count += 1
            trace["lineage_edges_dropped"] += count
            trace["coverage"] = "partial"
        else:
            raise ValueError("search_trace_limit")
        total = size(result)
    return result
