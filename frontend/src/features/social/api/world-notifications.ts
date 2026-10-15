import { requestSocialApi } from "@/lib/http/social-request";
import { ApiRequestError } from "@/lib/http/error-contract";
import type { NotificationScope, WorldNotificationCount, WorldNotificationPage, WorldNotificationReadAllResult, WorldUnreadCount } from "../types/world-notifications";

function validCount(value: unknown): value is number { return Number.isSafeInteger(value) && Number(value) >= 0; }
function object(value: unknown): value is Record<string, unknown> { return !!value && typeof value === "object" && !Array.isArray(value); }
const invalid = () => new Error("notification_response_invalid");
/** Permission/scope rejection is different from a transient refresh failure. */
export function notificationSnapshotRejected(error: unknown) {
  return error instanceof ApiRequestError && [401, 403, 404, 409].includes(error.status)
    || error instanceof Error && error.message === "notification_response_invalid";
}
function assertScope<T extends WorldNotificationCount>(value: T, scope: NotificationScope): T {
  if (!object(value) || !object(value.scope) || value.scope.world_id !== scope.world_id ||
      value.scope.recipient_world_character_id !== scope.recipient_world_character_id || !validCount(value.unread_count)) throw invalid();
  return value;
}
const path = (worldId: string) => `/worlds/${encodeURIComponent(worldId)}/notifications`;

export async function getWorldNotificationCount(scope: NotificationScope, signal: AbortSignal) {
  return assertScope(await requestSocialApi<WorldNotificationCount>(`${path(scope.world_id)}/unread-count`, { signal, cache: "no-store" }), scope);
}
export async function getWorldNotifications(scope: NotificationScope, signal: AbortSignal, cursor?: string | null) {
  const query = new URLSearchParams({ limit: "20" });
  if (cursor) query.set("cursor", cursor);
  const result = assertScope(await requestSocialApi<WorldNotificationPage>(`${path(scope.world_id)}?${query}`, { signal, cache: "no-store" }), scope);
  if (!Array.isArray(result.items) || !(result.next_cursor === null || typeof result.next_cursor === "string")) throw invalid();
  const ids = new Set<number>();
  for (const item of result.items) {
    if (!object(item) || !Number.isSafeInteger(item.id) || item.id <= 0 || ids.has(item.id) ||
        !["like", "reply", "quote", "mention", "repost", "follow"].includes(item.notification_type) ||
        !object(item.target) || !["post", "world_character"].includes(item.target.kind) || typeof item.target.can_open !== "boolean" ||
        !(item.read_at === null || typeof item.read_at === "string") || typeof item.created_at !== "string" ||
        !(item.preview_text === null || typeof item.preview_text === "string") ||
        !(item.actor_name === null || typeof item.actor_name === "string") ||
        !(item.actor_handle === null || typeof item.actor_handle === "string") ||
        !(item.actor_avatar_url === null || typeof item.actor_avatar_url === "string") ||
        typeof item.actor_deleted !== "boolean" ||
        !(item.actor_world_character_id === null || typeof item.actor_world_character_id === "string")) throw invalid();
    if (item.target.can_open && (item.target.kind === "post" ? typeof item.target.post_id !== "string" : typeof item.target.world_character_id !== "string")) throw invalid();
    ids.add(item.id);
  }
  return result;
}
export async function markAllWorldNotificationsRead(scope: NotificationScope, signal: AbortSignal) {
  const result = assertScope(await requestSocialApi<WorldNotificationReadAllResult>(`${path(scope.world_id)}/read-all`, {
    method: "POST", body: { recipient_world_character_id: scope.recipient_world_character_id }, signal, keepalive: true,
  }), scope);
  if (!validCount(result.marked_count) || !(result.read_at === null || typeof result.read_at === "string") ||
      !(result.through_notification_id === null || Number.isSafeInteger(result.through_notification_id) && result.through_notification_id > 0) ||
      (result.marked_count > 0 && (!result.read_at || result.through_notification_id === null)) ||
      (result.marked_count === 0 && result.read_at !== null)) throw invalid();
  return result;
}
export async function getWorldUnreadCounts(ids: string[], signal: AbortSignal) {
  const unique = [...new Set(ids)];
  if (!unique.length || unique.length > 50) throw invalid();
  const query = new URLSearchParams(unique.map(id => ["world_ids", id]));
  const result = await requestSocialApi<{ items: WorldUnreadCount[] }>(`/notifications/world-unread-counts?${query}`, { signal, cache: "no-store" });
  if (!object(result) || !Array.isArray(result.items) || result.items.length !== unique.length) throw invalid();
  const remaining = new Set(unique);
  for (const item of result.items) {
    if (!object(item) || typeof item.world_id !== "string" || !remaining.delete(item.world_id)) throw invalid();
    if (item.status === "available" ? typeof item.recipient_world_character_id !== "string" || !validCount(item.unread_count)
      : item.status !== "unavailable" || item.recipient_world_character_id !== null || item.unread_count !== null) throw invalid();
  }
  return result.items;
}
