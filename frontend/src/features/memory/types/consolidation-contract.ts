export const consolidationStates = ["preparing", "queued", "waiting_for_chat", "ai_running", "applying", "completed", "no_work", "partial_failed", "failed", "paused", "cancelled"] as const;
export type ConsolidationProgress = {
  request_id: string; effective_request_id: string; kind: string; accepted_at: string;
  state: typeof consolidationStates[number]; saved_count: number; remaining_count: number;
  job_count: number; completed_job_count: number; last_code: string | null;
};
export type ConsolidationStart = {
  idempotency_key: string; expected_version: number; expected_profile_version: number; expected_scope_version: number;
};
export const consolidationActive = (state: ConsolidationProgress["state"]) =>
  ["preparing", "queued", "waiting_for_chat", "ai_running", "applying"].includes(state);
