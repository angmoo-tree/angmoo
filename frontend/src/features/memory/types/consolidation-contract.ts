export const consolidationStates = ["preparing", "queued", "waiting_for_chat", "ai_running", "applying", "completed", "no_work", "partial_failed", "failed", "paused", "cancelled"] as const;
export type ConsolidationProgress = {
  request_id: string; effective_request_id: string; kind: string; accepted_at: string;
  state: typeof consolidationStates[number]; saved_count: number; remaining_count: number;
  job_count: number; completed_job_count: number; last_code: string | null;
  workflow_version?: 1; followup?: "relationships"; flow_state?: FlowState;
  relationship?: { state: string; request_id: string; target_count: number | null; memory_count: number | null;
    completed_count: number; changed_count: number; kept_count: number; excluded_memory_count?: number;
    projection_pending?: boolean; retryable?: boolean; next_attempt_at?: string | null; wait_reason?: string | null;
    last_code: string | null; completed_at: string | null };
};
export const flowStates = ["memory_running", "memory_failed", "memory_only_completed", "relationship_waiting", "relationship_running",
  "relationship_retry_needed", "relationship_paused", "completed", "no_work", "no_relationship_work"] as const;
export type FlowState = typeof flowStates[number];
export type ConsolidationCapability = { relationships: boolean; reason: string | null };
export type ConsolidationStart = {
  idempotency_key: string; expected_version: number; expected_profile_version: number; expected_scope_version: number;
  followup?: "relationships";
};
export const consolidationActive = (state: ConsolidationProgress["state"]) =>
  ["preparing", "queued", "waiting_for_chat", "ai_running", "applying"].includes(state);
export const workflowActive = (value: ConsolidationProgress) => value.flow_state
  ? ["memory_running", "relationship_waiting", "relationship_running", "relationship_retry_needed"].includes(value.flow_state)
  : consolidationActive(value.state);
