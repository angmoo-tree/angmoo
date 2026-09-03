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
  capabilities: { read: "available"; mutate: "not_available_in_p8_l_q" };
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
  capabilities: { read: "available"; mutate: "not_available_in_p8_l_q" };
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
  capabilities: { read: "available"; mutate: "not_available_in_p8_l_q" };
};

export type WorldChatEvidenceSummaryRead = {
  request_id: string;
  assistant_message_id: number;
  capability: "available" | "degraded";
  count: number;
};

export type WorldChatEvidenceItemRead = {
  reference: string;
  kind: "canonical_source" | "graph_relationship" | "graph_event";
  label: string;
  excerpt: string | null;
  occurred_at: string | null;
  availability: MemoryEvidenceAvailability;
  related_character: string | null;
  direction: "incoming" | "outgoing" | "contextual" | null;
  canonical_href: string | null;
};

export type WorldChatEvidenceRead = {
  schema_version: "world-chat-evidence.v1";
  request_id: string;
  route: string;
  retrieval_outcome: string;
  capability: "available" | "degraded";
  items: WorldChatEvidenceItemRead[];
};
