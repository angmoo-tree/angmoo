import type { MemoryScopeRead } from "./memory-contract";

export type MemoryProcessingSetting = {
  scope: MemoryScopeRead; version: number; memory_enabled: boolean;
  daily_enabled: boolean; local_time: string; timezone: string; shutdown_apply_enabled: boolean;
  next_due_at: string | null; last_applied_at: string | null;
  pending_count: number; blocked_count: number; applied_count: number;
  status: "idle" | "accepted" | "applying" | "saved" | "partial_error" | "closed" | "cancelled";
  revision?: number; actions?: import("./consolidation-contract").MaintenanceAction[]; error_code?: string | null;
  result: "accepted" | "empty" | null;
  resolved_request_key?: string | null;
  operation?: "pending_apply" | "blocked_recheck" | null;
  run_id?: string | null;
  run_state?: "pending" | "running" | "deferred" | "completed" | "error" | null;
  rejected_count?: number; skipped_count?: number;
  scope_busy?: boolean; can_recheck?: boolean;
};
export type MemorySaveRequest = { expected_version: number; idempotency_key: string };
export type MemoryProcessingUpdate = MemorySaveRequest & Pick<MemoryProcessingSetting,
  "daily_enabled" | "local_time" | "shutdown_apply_enabled">;

export type MemoryUnsavedExperience = {
  receipt_sequence: number; state_version: number; occurred_at: string; description: string | null;
  reason: "source_changed" | "access_unavailable" | "proof_unavailable" | "activation_closed" | "description_invalid" | "description_language_only" | "result_invalid" | "validation_failed";
  can_recheck: boolean; can_discard: boolean;
};
export type MemoryUnsavedExperiences = {
  scope: MemoryScopeRead; items: MemoryUnsavedExperience[]; next_cursor: string | null;
  blocked_count: number; scope_busy: boolean; can_recheck: boolean;
};
export type MemoryIndividualRecheckRequest = MemorySaveRequest & { expected_receipt_version: number };
export type MemoryDiscardRequest = { expected_receipt_version: number; idempotency_key: string };
export type MemoryDiscardResult = {
  scope: MemoryScopeRead; receipt_sequence: number; state: "discarded"; state_version: number;
  discarded_at: string; operation: "discard"; result: "discarded" | "already_discarded";
  resolved_request_key: string; pending_count: number; blocked_count: number;
};
