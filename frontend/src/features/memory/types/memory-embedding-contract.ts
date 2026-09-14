export type MemoryEmbeddingSetting = {
  scope: { world_id: string; subject_world_character_id: string };
  enabled: boolean;
  provider: "google";
  model: "gemini-embedding-2";
  credential_id: string | null;
  profile: string;
  version: number;
  ready: boolean;
  reason_code: string | null;
  runtime_status: "unknown" | "stopped" | "ready" | "recovering" | "degraded" | "vector_unavailable";
  available_credentials: { id: string; label: string }[];
};

export type MemoryEmbeddingUpdate = Pick<MemoryEmbeddingSetting, "enabled" | "provider" | "model" | "credential_id"> & { expected_version: number };
