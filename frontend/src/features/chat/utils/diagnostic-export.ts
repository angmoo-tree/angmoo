import type { RetrievalDiagnosticsRead } from "../types/retrieval-diagnostics";

function selectFields(row: object, keys: readonly string[]) {
  return Object.fromEntries(keys.filter(key => Object.hasOwn(row, key)).map(key => [key, (row as Record<string, unknown>)[key]]));
}
function exportSearchTrace(trace: NonNullable<RetrievalDiagnosticsRead["search_trace"]>) {
  return {
    ...selectFields(trace, ["version", "coverage", "stage_events_dropped", "lineage_edges_dropped", "aliases_dropped", "detail_rows_dropped"]),
    stages: trace.stages.slice(0, 48).map(row => selectFields(row, [
      "axis", "stage", "clock_domain", "state", "start_ms", "end_ms", "elapsed_ms",
      "budget_at_start_ms", "remaining_at_end_ms", "deadline_exceeded"])),
    terminals: trace.terminals.slice(0, 2).map(row => ({
      ...selectFields(row, ["axis", "axis_status", "terminal_state", "last_observed_stage", "cause_certainty", "worker_started",
        "nn_query_started", "result_received", "terminal_observed", "terminate_sent", "kill_sent", "joined",
        "worker_exit_code", "termination_reason", "cleanup_error_code", "eligible_vector_count", "requested_generation",
        "observed_generation", "requested_profile", "observed_schema_revision", "generation_match", "metadata_status", "stage_events_dropped"]),
      failure: row.failure ? selectFields(row.failure, ["failure_code", "failure_stage", "exception_kind", "sqlite_error_code"]) : null,
    })),
    lineage: trace.lineage.slice(0, 160).map(row => selectFields(row, [
      "stage", "action", "axis", "document_ref", "identity_ref", "memory_ref", "source_ref",
      "record_ref", "evidence_ref", "key_ref", "related_ref", "rank", "count", "reason"])),
  };
}


export function diagnosticSnapshotMatches(data: RetrievalDiagnosticsRead, worldId: string, threadId: string, requestId: string) {
  return data.world_id === worldId && data.thread_id === threadId &&
    (!requestId || data.request_id === requestId) && !!data.request &&
    data.request.request_id === data.request_id && data.request.state === data.request_state;
}

export function diagnosticExport(data: RetrievalDiagnosticsRead, worldId: string, threadId: string, requestId: string, now = new Date()) {
  if (!diagnosticSnapshotMatches(data, worldId, threadId, requestId) || !data.request) throw new Error("diagnostic_snapshot_mismatch");
  const request = data.request;
  const summary = data.record?.events.findLast(row => row.event === "decision_summary");
  return {
    export_version: "angmoo-query-diagnostics.export.v2",
    exported_at: now.toISOString(),
    request: { request_id: request.request_id, created_at: request.created_at, state: request.state,
      user_message_id: request.user_message_id, attempt_number: request.attempt_number, retry_of_request_id: request.retry_of_request_id },
    basic_status: data.status,
    record: data.record,
    details_status: data.details === null && !data.search_trace ? "not_available" : "available",
    details: data.details,
    search_trace: data.search_trace ? exportSearchTrace(data.search_trace) : null,
    detail_availability: data.detail_availability ?? "unknown",
    capture_at_export: { enabled: data.capture.enabled, remaining: data.capture.remaining, expires_at: data.capture.expires_at },
    completeness: { omitted_events: data.record?.omitted_events ?? null,
      detail_captured: typeof summary?.detail_captured === "boolean" ? summary.detail_captured : null,
      detail_omitted: typeof summary?.detail_omitted === "number" ? summary.detail_omitted : null,
      trace_complete: typeof summary?.trace_complete === "boolean" ? summary.trace_complete : null },
  };
}

export function diagnosticFilename(requestId: string, createdAt: string) {
  return `angmoo-query-diagnostics-${createdAt}-${requestId}`.replace(/[^a-zA-Z0-9._-]/g, "_") + ".json";
}
