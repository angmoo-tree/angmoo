import type { RetrievalDiagnosticsRead } from "../types/retrieval-diagnostics";

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
    export_version: "angmoo-query-diagnostics.export.v1",
    exported_at: now.toISOString(),
    request: { request_id: request.request_id, created_at: request.created_at, state: request.state,
      user_message_id: request.user_message_id, attempt_number: request.attempt_number, retry_of_request_id: request.retry_of_request_id },
    basic_status: data.status,
    record: data.record,
    details_status: data.details === null ? "not_available" : "available",
    details: data.details,
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
