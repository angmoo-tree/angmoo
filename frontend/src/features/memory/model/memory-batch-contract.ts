export type MemoryBatchSetting = {
  scope: { world_id: string; subject_world_character_id: string };
  version: number;
  profile_version: number;
  memory_enabled: boolean;
  ai_enabled: boolean;
  shutdown_enabled: boolean;
  schedule_enabled: boolean;
  local_time: string;
  timezone: string;
  next_due_at: string | null;
  model_id: string | null;
  pending_count: number;
  status: "disabled" | "paused" | "waiting" | "running" | "pending" | "attention" | "completed";
  last_code: string | null;
  last_completed_at: string | null;
  available_models: string[];
};

export type MemoryBatchUpdate = Pick<MemoryBatchSetting,
  "ai_enabled" | "shutdown_enabled" | "schedule_enabled" | "local_time" | "model_id"
> & {
  expected_version: number;
  expected_profile_version: number;
  consent_version: string | null;
  idempotency_key: string;
};
