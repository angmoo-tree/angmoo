import type { SearchDiagnosticTrace } from "./search-trace";

export type TemporalDiagnostic = {
  time_resolution: "resolved" | "invalid" | "ambiguous" | "not_requested";
  requested_kind: string | null; validation_code: string | null; field_path: string | null;
  reference_utc: string | null; timezone: string | null; local_date: string | null;
  context_digest: string | null; query_origin: "model_search_text" | "original_user_message" | "none";
  route_change_reason: string | null; time_filter_applied: boolean;
  applied_from: string | null; applied_to: string | null; retrieval_executed: boolean;
};
export type DbWriteAttempt = {
  start_offset_ms: number | null; end_offset_ms: number | null;
  sequence: number; stage: "admission" | "workflow_checkpoint" | "diagnostic_persist" | "response_finalize" | "cancel_or_failure" | "post_commit";
  database_id: string; attempt: number; basis: "begin_immediate" | "write_span_only";
  outcome: "committed" | "rolled_back" | "busy" | "partial";
  checkout_ms: number | null; acquire_ms: number | null; hold_ms: number | null;
  commit_ms: number | null; rollback_ms: number | null; write_span_ms: number | null;
  retry_wait_ms: number | null; diagnostic_persist_ms: number | null;
};
export type DbWriteDiagnostics = {
  version: "chat-db-write.v1"; request_id: string; attempt_number: number;
  coverage: "complete" | "partial" | "write_span_only" | "no_writes";
  attempts: DbWriteAttempt[]; omitted_attempts: number; completed_attempts: number;
  longest_hold_ms: number | null; total_hold_ms: number | null; total_write_span_ms: number | null;
  retry_count: number; retry_wait_ms: number | null;
};

export type DiagnosticRequest = {
  request_id: string; created_at: string; state: string; user_message_id: number;
  attempt_number: number; retry_of_request_id: string | null;
};
export type DiagnosticRequestList = {
  world_id: string; thread_id: string; items: DiagnosticRequest[]; next_cursor: string | null;
};
export type RetrievalDiagnosticsRead = {
  world_id: string; thread_id: string; request_id: string | null; request_state: string | null;
  request: DiagnosticRequest | null;
  status: "available" | "not_recorded" | "unavailable" | "expired";
  record: { version: "chat-retrieval-diagnostics.v1"; events: Record<string, string | number | boolean>[]; omitted_events: number } | null;
  capture: { enabled: boolean; remaining: number; expires_at: string | null };
  details: Record<string, string | number>[] | null;
  search_trace?: SearchDiagnosticTrace | null;
  temporal_recall?: TemporalDiagnostic | null;
  db_write?: DbWriteDiagnostics | null;
  detail_availability?: "available" | "pending" | "not_captured" | "not_retained" | "unsupported" | "unknown";
};
