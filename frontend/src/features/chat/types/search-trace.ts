export type SearchStage = {
  axis: "fts" | "vector"; stage: string; clock_domain: "parent" | "child";
  state: "running" | "completed" | "failed" | "cancelled" | "unknown";
  start_ms: number; end_ms: number | null; elapsed_ms: number | null;
  budget_at_start_ms: number; remaining_at_end_ms: number | null; deadline_exceeded: boolean;
};
export type SearchFailure = {
  failure_code: string; failure_stage: string | null; exception_kind: string; sqlite_error_code: number | null;
};
export type SearchTerminal = {
  axis_status?: "ready" | "partial" | "disabled" | "unavailable" | "cancelled" | null;
  axis: "fts" | "vector"; terminal_state: string; failure: SearchFailure | null;
  last_observed_stage: string | null; cause_certainty: string;
  worker_started: boolean; nn_query_started: boolean | null; result_received: boolean; terminal_observed: boolean;
  terminate_sent: boolean; kill_sent: boolean; joined: boolean; worker_exit_code: number | null;
  termination_reason: string; cleanup_error_code: string | null;
  eligible_vector_count: number | null; requested_generation: string | null; observed_generation: string | null;
  requested_profile: string | null; observed_schema_revision: string | null; generation_match: boolean | null;
  metadata_status: string; stage_events_dropped: number;
};
export type SearchLineage = {
  stage: string; action: string; axis: string | null; document_ref: string | null;
  identity_ref: string | null; memory_ref: string | null; source_ref: string | null;
  record_ref: string | null; evidence_ref: string | null; key_ref: string | null; related_ref: string | null;
  rank: number | null; count: number | null; reason: string | null;
};
export type SearchDiagnosticTrace = {
  version: "search-diagnostic-trace.v1"; coverage: "complete" | "partial";
  stages: SearchStage[]; terminals: SearchTerminal[]; lineage: SearchLineage[];
  stage_events_dropped: number; lineage_edges_dropped: number; aliases_dropped: number;
  detail_rows_dropped?: number;
};
