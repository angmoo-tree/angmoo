import { apiRequest, ApiRequestError } from "@/lib/http/api-request";
import type { WorldCharacterCapabilities, WorldCharacterDashboardItem, WorldCharacterDashboardRead } from "../types/world-character-dashboard";
import type { WorldCharacterPublicProfile } from "../types/world-character-profile";

export async function getWorldCharacterDashboard(worldId: string, options: { signal?: AbortSignal } = {}) {
  return decodeWorldCharacterDashboard(await apiRequest<unknown>(`/worlds/${encodeURIComponent(worldId)}/character-dashboard`, options), worldId);
}

export async function setWorldCharacterAutonomy(worldId: string, worldCharacterId: string, enabled: boolean, revision: number, options: { signal?: AbortSignal } = {}) {
  const payload = await apiRequest<unknown>(`${worldCharacterManagementApiPath(worldId, worldCharacterId)}/${enabled ? "activate" : "deactivate"}`,
    { ...options, method: "POST", body: { expected_revision: revision } });
  const result = decodeWorldCharacterDashboard(payload, worldId);
  if (!result.items.some((item) => item.profile.world_character_id === worldCharacterId)) invalidWorldCharacterRead();
  return result;
}

export function worldCharacterManagementApiPath(worldId: string, worldCharacterId: string) {
  return `/worlds/${encodeURIComponent(worldId)}/world-characters/${encodeURIComponent(worldCharacterId)}`;
}

export function invalidWorldCharacterRead(): never {
  throw new ApiRequestError("Invalid World character response.", 502, "world_character_scope_mismatch");
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

export function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

export function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

export function decodeWorldCharacterCapabilities(value: unknown): WorldCharacterCapabilities {
  if (!isRecord(value) || !["can_activate", "can_deactivate", "can_run_now", "can_edit_profile", "can_edit_settings", "can_view_graph"]
    .every((key) => typeof value[key] === "boolean") || !isNullableString(value.reason)) invalidWorldCharacterRead();
  return value as WorldCharacterCapabilities;
}

export function decodeWorldCharacterProfile(value: unknown, worldId: string): WorldCharacterPublicProfile {
  if (!isRecord(value) || value.schema_version !== "world-character-profile-v1" || value.world_id !== worldId
    || typeof value.world_character_id !== "string" || !value.world_character_id || typeof value.character_id !== "string" || !value.character_id
    || typeof value.display_name !== "string" || !isNullableString(value.handle) || !isNullableString(value.avatar_url)
    || !isNullableString(value.banner_url) || typeof value.intro !== "string" || !isNullableString(value.role_key)
    || !["autonomous", "owner_controlled"].includes(String(value.control_mode)) || value.status !== "active" || value.profile_capability !== "available") invalidWorldCharacterRead();
  return value as WorldCharacterPublicProfile;
}

export function decodeWorldCharacterDashboardItem(value: unknown, worldId: string): WorldCharacterDashboardItem {
  if (!isRecord(value) || !isNonNegativeInteger(value.revision) || typeof value.autonomous_enabled !== "boolean"
    || !isRecord(value.status) || typeof value.status.state !== "string" || !isNullableString(value.status.reason)
    || !isNullableString(value.next_activity_at)) invalidWorldCharacterRead();
  const profile = decodeWorldCharacterProfile(value.profile, worldId);
  const capabilities = decodeWorldCharacterCapabilities(value.capabilities);
  if (profile.control_mode === "owner_controlled" && (value.autonomous_enabled || capabilities.can_activate || capabilities.can_deactivate || capabilities.can_run_now)) invalidWorldCharacterRead();
  if (value.settings !== null && (!isRecord(value.settings)
    || !["active_hours_start", "active_hours_end", "timezone"].every((key) => typeof (value.settings as Record<string, unknown>)[key] === "string")
    || !["activity_interval_minutes", "max_posts_per_day", "max_comments_per_day"].every((key) => isNonNegativeInteger((value.settings as Record<string, unknown>)[key])))) invalidWorldCharacterRead();
  if (value.recent_activity !== null && (!isRecord(value.recent_activity)
    || typeof value.recent_activity.action_type !== "string" || typeof value.recent_activity.occurred_at !== "string"
    || !isNullableString(value.recent_activity.post_id) || !isNullableString(value.recent_activity.title))) invalidWorldCharacterRead();
  return { ...value, profile, capabilities } as WorldCharacterDashboardItem;
}

export function decodeWorldCharacterDashboard(payload: unknown, worldId: string): WorldCharacterDashboardRead {
  if (!isRecord(payload) || payload.contract_version !== "world-character-dashboard-v1" || payload.world_id !== worldId
    || !Array.isArray(payload.items) || !isRecord(payload.summary)
    || !["total", "enabled", "disabled", "users"].every((key) => isNonNegativeInteger((payload.summary as Record<string, unknown>)[key]))) invalidWorldCharacterRead();
  const items = payload.items.map((item) => decodeWorldCharacterDashboardItem(item, worldId));
  const ids = new Set(items.map((item) => item.profile.world_character_id));
  const summary = payload.summary as WorldCharacterDashboardRead["summary"];
  const users = items.filter((item) => item.profile.control_mode === "owner_controlled").length;
  const enabled = items.filter((item) => item.profile.control_mode === "autonomous" && item.autonomous_enabled).length;
  if (ids.size !== items.length || summary.total !== items.length || summary.users !== users || summary.enabled !== enabled
    || summary.disabled !== items.length - users - enabled) invalidWorldCharacterRead();
  return { contract_version: "world-character-dashboard-v1", world_id: worldId, summary, items };
}
