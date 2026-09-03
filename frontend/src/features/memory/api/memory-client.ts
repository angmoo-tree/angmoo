import { clearStoredUser, notifyAuthChanged } from "@/shared/auth/public";
import { runtimeFetch } from "@/shared/runtime/public";

import type {
  MemoryItemDetailRead,
  MemoryItemListRead,
  MemorySettingRead,
  WorldChatEvidenceRead,
} from "../model/memory-contract";

export class MemoryApiError extends Error {
  constructor(readonly status: number, readonly detail: string) {
    super(detail);
    this.name = "MemoryApiError";
  }
}

export function getMemorySetting(
  worldId: string,
  subjectId: string,
  options: { signal?: AbortSignal } = {},
) {
  return requestMemoryApi<MemorySettingRead>(
    `${scopePath(worldId, subjectId)}/memory/settings`,
    options,
  ).then((read) => {
    if (
      read.schema_version !== "memory-setting-read.v1" ||
      !matchesScope(read.scope, worldId, subjectId) ||
      typeof read.configured !== "boolean" ||
      typeof read.enabled !== "boolean" ||
      !Number.isInteger(read.retention_days) ||
      read.retention_days < 1 ||
      !["none", "optional-configured"].includes(read.provider_mode) ||
      !Number.isInteger(read.version) ||
      read.version < 0 ||
      read.capabilities?.read !== "available" ||
      read.capabilities?.mutate !== "not_available_in_p8_l_q"
    ) throw new MemoryApiError(502, "memory_setting_scope_mismatch");
    return read;
  });
}

export function listMemoryItems(
  worldId: string,
  subjectId: string,
  options: { cursor?: string | null; signal?: AbortSignal } = {},
) {
  const query = new URLSearchParams({ limit: "20" });
  if (options.cursor) query.set("cursor", options.cursor);
  return requestMemoryApi<MemoryItemListRead>(
    `${scopePath(worldId, subjectId)}/memories?${query}`,
    { signal: options.signal },
  ).then((read) => {
    if (
      read.schema_version !== "memory-item-list.v1" ||
      !matchesScope(read.scope, worldId, subjectId) ||
      typeof read.memory_enabled !== "boolean" ||
      !Array.isArray(read.items) ||
      read.items.some((item) => !memorySummaryMatches(item)) ||
      (read.next_cursor !== null && typeof read.next_cursor !== "string") ||
      read.capabilities?.read !== "available" ||
      read.capabilities?.mutate !== "not_available_in_p8_l_q"
    ) throw new MemoryApiError(502, "memory_list_scope_mismatch");
    return read;
  });
}

export function getMemoryItem(
  worldId: string,
  subjectId: string,
  memoryId: string,
  options: { signal?: AbortSignal } = {},
) {
  return requestMemoryApi<MemoryItemDetailRead>(
    `${scopePath(worldId, subjectId)}/memories/${encodeURIComponent(memoryId)}`,
    options,
  ).then((read) => {
    if (
      read.schema_version !== "memory-item-detail.v1" ||
      read.id !== memoryId ||
      !matchesScope(read.scope, worldId, subjectId) ||
      !memorySummaryMatches(read) ||
      !Array.isArray(read.evidence) ||
      read.evidence.some((item) => !memoryEvidenceMatches(item, worldId)) ||
      typeof read.provenance_summary !== "string" ||
      read.capabilities?.read !== "available" ||
      read.capabilities?.mutate !== "not_available_in_p8_l_q"
    ) throw new MemoryApiError(502, "memory_detail_scope_mismatch");
    return read;
  });
}

export function getWorldChatEvidence(
  worldId: string,
  threadId: string,
  requestId: string,
  options: { signal?: AbortSignal } = {},
) {
  return requestMemoryApi<WorldChatEvidenceRead>(
    `/worlds/${encodeURIComponent(worldId)}/chat/threads/${encodeURIComponent(threadId)}/requests/${encodeURIComponent(requestId)}/evidence`,
    options,
  ).then((read) => {
    if (
      read.schema_version !== "world-chat-evidence.v1" ||
      read.request_id !== requestId ||
      typeof read.route !== "string" ||
      typeof read.retrieval_outcome !== "string" ||
      !["available", "degraded"].includes(read.capability) ||
      !Array.isArray(read.items) ||
      read.items.length > 12 ||
      read.items.some((item) => !chatEvidenceMatches(item, worldId))
    ) throw new MemoryApiError(502, "chat_evidence_scope_mismatch");
    return read;
  });
}

async function requestMemoryApi<T>(
  path: string,
  options: { signal?: AbortSignal },
): Promise<T> {
  const response = await runtimeFetch(`/api/backend${path}`, {
    cache: "no-store",
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    signal: options.signal,
  });
  const payload = (await response.json().catch(() => null)) as unknown;
  if (!response.ok) {
    if (response.status === 401) {
      clearStoredUser();
      notifyAuthChanged();
    }
    throw new MemoryApiError(response.status, errorDetail(payload, `http_${response.status}`));
  }
  return payload as T;
}

function scopePath(worldId: string, subjectId: string) {
  return `/worlds/${encodeURIComponent(worldId)}/world-characters/${encodeURIComponent(subjectId)}`;
}

function matchesScope(
  scope: { world_id?: unknown; subject_world_character_id?: unknown },
  worldId: string,
  subjectId: string,
) {
  return scope?.world_id === worldId && scope.subject_world_character_id === subjectId;
}

function memorySummaryMatches(value: unknown) {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<MemoryItemDetailRead>;
  return (
    typeof item.id === "string" &&
    typeof item.summary === "string" &&
    typeof item.memory_kind === "string" &&
    ["active", "expired", "superseded", "deleted"].includes(item.lifecycle ?? "") &&
    typeof item.formed_at === "string" &&
    typeof item.valid_from === "string" &&
    (item.valid_until === null || typeof item.valid_until === "string") &&
    typeof item.pinned === "boolean" &&
    (item.superseded_by_memory_id === null || typeof item.superseded_by_memory_id === "string") &&
    Number.isInteger(item.retention_days) && (item.retention_days ?? 0) > 0 &&
    Number.isInteger(item.version) && (item.version ?? 0) >= 1 &&
    relatedCharacterMatches(item.related_character)
  );
}

function memoryEvidenceMatches(value: unknown, worldId: string) {
  if (!value || typeof value !== "object") return false;
  const item = value as MemoryItemDetailRead["evidence"][number];
  return (
    typeof item.source_kind === "string" &&
    typeof item.source_label === "string" &&
    typeof item.source_created_at === "string" &&
    ["available", "deleted", "unavailable"].includes(item.availability) &&
    (item.excerpt === null || typeof item.excerpt === "string") &&
    relatedCharacterMatches(item.related_character) &&
    safeProductHref(item.canonical_href, worldId)
  );
}

function chatEvidenceMatches(value: unknown, worldId: string) {
  if (!value || typeof value !== "object") return false;
  const item = value as WorldChatEvidenceRead["items"][number];
  return (
    typeof item.reference === "string" &&
    ["canonical_source", "graph_relationship", "graph_event"].includes(item.kind) &&
    typeof item.label === "string" &&
    (item.excerpt === null || typeof item.excerpt === "string") &&
    (item.occurred_at === null || typeof item.occurred_at === "string") &&
    ["available", "deleted", "unavailable"].includes(item.availability) &&
    (item.related_character === null || typeof item.related_character === "string") &&
    (item.direction === null || ["incoming", "outgoing", "contextual"].includes(item.direction)) &&
    safeProductHref(item.canonical_href, worldId)
  );
}

function relatedCharacterMatches(value: unknown) {
  if (value === null) return true;
  if (!value || typeof value !== "object") return false;
  const related = value as { display_name?: unknown; direction?: unknown };
  return typeof related.display_name === "string" &&
    ["incoming", "outgoing", "contextual"].includes(String(related.direction));
}

function safeProductHref(value: string | null, worldId: string) {
  return value === null || (
    typeof value === "string" &&
    (
      value.startsWith(`/worlds/${encodeURIComponent(worldId)}/`) ||
      value.startsWith("/memory?")
    ) &&
    !value.includes("\\")
  );
}

function errorDetail(payload: unknown, fallback: string) {
  return payload && typeof payload === "object" && "detail" in payload &&
    typeof payload.detail === "string" ? payload.detail : fallback;
}
