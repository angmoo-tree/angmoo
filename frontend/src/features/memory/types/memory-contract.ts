export const evidenceDisplayKeys = ["kind", "action", "actor", "counterpart", "truncated", "root_title", "root_body", "parent_title", "parent_body", "title", "body", "thought", "thought_truncated", "thought_status", "thought_unrecorded", "motivation", "emotion", "intensity"] as const;
export type EvidenceDisplayKey = typeof evidenceDisplayKeys[number];
export type MemoryLifecycle = "active" | "expired" | "superseded" | "deleted";
export type MemoryEvidenceAvailability = "available" | "deleted" | "unavailable";

export type MemoryScopeRead = {
  world_id: string;
  subject_world_character_id: string;
};

export type MemoryRelatedCharacterRead = {
  display_name: string;
  direction: "incoming" | "outgoing" | "contextual";
};

export type MemorySettingRead = {
  schema_version: "memory-setting-read.v1";
  scope: MemoryScopeRead;
  configured: boolean;
  enabled: boolean;
  retention_days: number;
  provider_mode: "none" | "optional-configured";
  version: number;
  capabilities: { read: "available"; mutate: "available" };
};

export type MemoryItemSummaryRead = {
  id: string;
  memory_kind: string;
  summary: string;
  lifecycle: MemoryLifecycle;
  formed_at: string;
  valid_from: string;
  valid_until: string | null;
  pinned: boolean;
  superseded_by_memory_id: string | null;
  retention_days: number;
  related_character: MemoryRelatedCharacterRead | null;
  version: number;
};

export type MemoryItemListRead = {
  schema_version: "memory-item-list.v1";
  scope: MemoryScopeRead;
  memory_enabled: boolean;
  items: MemoryItemSummaryRead[];
  next_cursor: string | null;
  capabilities: { read: "available"; mutate: "available" };
};

export type MemoryEvidenceRead = {
  source_kind: string;
  source_label: string;
  source_created_at: string;
  availability: MemoryEvidenceAvailability;
  excerpt: string | null;
  related_character: MemoryRelatedCharacterRead | null;
  canonical_href: string | null;
};

export type MemoryItemDetailRead = MemoryItemSummaryRead & {
  schema_version: "memory-item-detail.v1";
  scope: MemoryScopeRead;
  evidence: MemoryEvidenceRead[];
  provenance_summary: string;
  episode?: EpisodeDetailRead | null;
  capabilities: { read: "available"; mutate: "available" };
};

export type EpisodeDetailRead = {
  representation: "episode_v1" | "activity_situation_v1" | "legacy_summary";
  snapshot_status?: "historical_snapshot" | "partial_snapshot" | "snapshot_unavailable" | null;
  experience_state?: "action_succeeded" | "observed_action_failed" | null;
  partial: boolean;
  omitted_units: number;
  followup_count: number;
  units: {
    sources: { role: string; text: string | null; status: "verified" | "missing" | "changed" | "unavailable"; author_label?: string | null; author_role?: string | null; occurred_at?: string | null }[];
    thought: { text: string | null; status: "recorded" | "missing" | "invalid"; truncated: boolean } | null;
    legacy_declaration: string | null;
  }[];
};

export type MemorySettingMutationRead = {
  schema_version: "memory-setting-mutation.v1";
  outcome: "updated" | "reused";
  setting: MemorySettingRead;
  projection_cleanup: "automatic_after_commit";
};

export type MemoryItemMutationRead = {
  schema_version: "memory-item-mutation.v1";
  operation: "pin" | "unpin" | "correct" | "delete";
  outcome: "updated" | "reused" | "deleted";
  scope: MemoryScopeRead;
  item: MemoryItemSummaryRead;
  replaced_memory_id: string | null;
  projection_cleanup: "automatic_after_commit";
};

export type WorldChatEvidenceSummaryRead = {
  request_id: string;
  assistant_message_id: number;
  capability: "available" | "degraded";
  count: number;
};

export type WorldChatEvidenceItemRead = {
  display_segments?: { key: EvidenceDisplayKey | null; text: string }[] | null;
  reference: string;
  kind: "canonical_source" | "graph_relationship" | "graph_event" | "today_sns_activity" | "episode_memory" | "current_image_analysis";
  episode?: EpisodeDetailRead | null;
  label: string;
  excerpt: string | null;
  occurred_at: string | null;
  availability: MemoryEvidenceAvailability;
  time_provenance?: { kind: "event" | "interval" | "recorded" | "unknown"; event_from: string | null; event_to: string | null; recorded_at: string | null } | null;
  related_character: string | null;
  direction: "incoming" | "outgoing" | "contextual" | null;
  canonical_href: string | null;
  relationship_change?: "same" | "changed" | "not_checked" | null;
  relationship_projection?: {
    familiarity: number; affinity: number; trust: number; tension: number; interactions: number;
    relationship_label: string | null; perception: string | null;
  } | null;
};

export type WorldChatEvidenceRead = {
  schema_version: "world-chat-evidence.v1";
  request_id: string;
  route: string;
  retrieval_outcome: string;
  capability: "available" | "degraded";
  items: WorldChatEvidenceItemRead[];
  current_context?: WorldChatEvidenceItemRead[];
  retrieval_limitations?: { partial_axes: ("canonical" | "graph" | "image")[]; degraded_reason: string | null } | null;
  read_limitations?: ("historical_unverified" | "current_unavailable" | "read_unavailable")[] | null;
};
