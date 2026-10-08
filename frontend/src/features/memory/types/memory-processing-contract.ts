import type { MemoryScopeRead } from "./memory-contract";

export type MemoryProcessingSetting = {
  scope: MemoryScopeRead; version: number; memory_enabled: boolean;
  daily_enabled: boolean; local_time: string; timezone: string; shutdown_apply_enabled: boolean;
  next_due_at: string | null; last_applied_at: string | null;
  pending_count: number; blocked_count: number; applied_count: number;
  status: "idle" | "accepted" | "applying" | "saved" | "partial_error";
  result: "accepted" | "empty" | null;
  resolved_request_key?: string | null;
};
export type MemorySaveRequest = { expected_version: number; idempotency_key: string };
export type MemoryProcessingUpdate = MemorySaveRequest & Pick<MemoryProcessingSetting,
  "daily_enabled" | "local_time" | "shutdown_apply_enabled">;
