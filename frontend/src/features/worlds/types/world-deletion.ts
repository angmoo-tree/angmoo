export type WorldDeletionState = "accepted" | "draining" | "purging" | "cleaning" | "verifying" | "retry_wait" | "failed" | "completed";
export type WorldDeletionReceipt = {
  request_id: string; world_id: string; state: WorldDeletionState;
  accepted_at: string; completed_at: string | null; can_retry: boolean;
};
export type WorldDeletionPreview = {
  world_id: string; stored_name: string; row_version: number;
  can_delete: boolean; is_default_space: boolean; export_available: boolean;
};
export type WorldDeletionCommand = {
  expected_row_version: number; confirmed_name: string; consent: true; idempotency_key: string;
};
