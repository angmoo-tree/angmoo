export type RetrievalDiagnosticsRead = {
  world_id: string; thread_id: string; request_id: string | null; request_state: string | null;
  status: "available" | "not_recorded" | "unavailable" | "expired";
  record: { version: "chat-retrieval-diagnostics.v1"; events: Record<string, string | number | boolean>[]; omitted_events: number } | null;
  capture: { enabled: boolean; remaining: number; expires_at: string | null };
  details: Record<string, string | number>[] | null;
};
