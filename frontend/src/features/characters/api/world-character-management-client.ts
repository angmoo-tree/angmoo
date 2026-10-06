import { apiRequest } from "@/lib/http/api-request";
import type { WorldCharacterManagementRead, WorldCharacterProfileValues, WorldCharacterSettingsRead, WorldCharacterSettingsValues, WorldCharacterRunNowRead } from "../types/world-character-management";
import type { AgentProfileMediaUploadInput } from "../types/agents";
import { decodeWorldCharacterCapabilities, decodeWorldCharacterDashboardItem, invalidWorldCharacterRead, isNonNegativeInteger, isNullableString, isRecord, worldCharacterManagementApiPath } from "./world-character-dashboard-client";

export async function getWorldCharacterManagement(worldId: string, worldCharacterId: string, options: { signal?: AbortSignal } = {}) {
  return decodeManagement(await apiRequest<unknown>(`${worldCharacterManagementApiPath(worldId, worldCharacterId)}/management`, options), worldId, worldCharacterId);
}

export async function getWorldCharacterSettings(worldId: string, worldCharacterId: string, options: { signal?: AbortSignal } = {}) {
  return decodeSettings(await apiRequest<unknown>(`${worldCharacterManagementApiPath(worldId, worldCharacterId)}/settings`, options), worldId, worldCharacterId);
}

export async function updateWorldCharacterProfile(worldId: string, worldCharacterId: string, revision: number, values: Partial<WorldCharacterProfileValues>, options: { signal?: AbortSignal } = {}) {
  return decodeManagement(await apiRequest<unknown>(`${worldCharacterManagementApiPath(worldId, worldCharacterId)}/profile`, {
    ...options, method: "PATCH", body: { expected_revision: revision, ...values },
  }), worldId, worldCharacterId);
}

export async function updateWorldCharacterSettings(worldId: string, worldCharacterId: string, revision: number, settings: Partial<WorldCharacterSettingsValues>, options: { signal?: AbortSignal } = {}) {
  return decodeSettings(await apiRequest<unknown>(`${worldCharacterManagementApiPath(worldId, worldCharacterId)}/settings`, {
    ...options, method: "PATCH", body: { expected_revision: revision, settings },
  }), worldId, worldCharacterId);
}

export async function uploadWorldCharacterProfileMedia(worldId: string, worldCharacterId: string, revision: number, media: AgentProfileMediaUploadInput, options: { signal?: AbortSignal } = {}) {
  return decodeManagement(await apiRequest<unknown>(`${worldCharacterManagementApiPath(worldId, worldCharacterId)}/profile/media`, {
    ...options, method: "POST", body: { expected_revision: revision, media_type: media.media_type, content_type: media.content_type, data_base64: media.data_base64 },
  }), worldId, worldCharacterId);
}

export async function runWorldCharacterNow(worldId: string, worldCharacterId: string, characterId: string, revision: number, options: { signal?: AbortSignal } = {}) {
  const payload = await apiRequest<unknown>(`${worldCharacterManagementApiPath(worldId, worldCharacterId)}/run-now`, {
    ...options, method: "POST", body: { expected_revision: revision },
  });
  if (!isRecord(payload) || payload.contract_version !== "world-character-run-now-v1" || payload.world_id !== worldId
    || payload.world_character_id !== worldCharacterId || payload.character_id !== characterId || !isNonNegativeInteger(payload.revision)
    || !isRecord(payload.run) || payload.run.character_id !== characterId
    || !["run_id", "status", "agent_id", "session_key"].every((key) => typeof (payload.run as Record<string, unknown>)[key] === "string")
    || !isNullableString(payload.run.summary) || !isNullableString(payload.run.post_id) || !isRecord(payload.run.gateway_result)) invalidWorldCharacterRead();
  return payload as WorldCharacterRunNowRead;
}

export function decodeManagement(payload: unknown, worldId: string, worldCharacterId: string): WorldCharacterManagementRead {
  if (!isRecord(payload) || payload.contract_version !== "world-character-management-v1" || payload.world_id !== worldId
    || payload.world_character_id !== worldCharacterId || typeof payload.character_id !== "string" || typeof payload.can_manage !== "boolean") invalidWorldCharacterRead();
  const item = decodeWorldCharacterDashboardItem(payload.item, worldId);
  if (item.profile.world_character_id !== worldCharacterId || item.profile.character_id !== payload.character_id
    || (!payload.can_manage && (item.capabilities.can_edit_profile || item.capabilities.can_edit_settings))) invalidWorldCharacterRead();
  return { ...payload, item } as WorldCharacterManagementRead;
}

export function decodeSettings(payload: unknown, worldId: string, worldCharacterId: string): WorldCharacterSettingsRead {
  if (!isRecord(payload) || payload.contract_version !== "world-character-settings-v1" || payload.world_id !== worldId
    || payload.world_character_id !== worldCharacterId || !isNonNegativeInteger(payload.revision) || !isRecord(payload.profile)
    || !["display_name", "intro"].every((key) => typeof (payload.profile as Record<string, unknown>)[key] === "string")
    || !["handle", "avatar_url", "banner_url"].every((key) => isNullableString((payload.profile as Record<string, unknown>)[key]))
    || !isRecord(payload.settings)) invalidWorldCharacterRead();
  const settings = payload.settings;
  if (!["personality", "speech_style", "worldview", "character_background", "topic_preferences", "safety_rules", "active_hours_start", "active_hours_end"].every((key) => typeof settings[key] === "string")
    || !["activity_interval_minutes", "max_posts_per_day", "max_comments_per_day"].every((key) => isNonNegativeInteger(settings[key]))
    || !["generation_model", "image_model", "image_style", "appearance_prompt"].every((key) => !(key in settings) || isNullableString(settings[key]))) invalidWorldCharacterRead();
  for (const key of ["supported_generation_models", "supported_image_models"] as const) {
    const options = payload[key];
    if (!Array.isArray(options) || !options.every(option => isRecord(option) && typeof option.value === "string"
      && option.value.length > 0 && typeof option.label === "string" && typeof option.enabled === "boolean" && isNullableString(option.reason))
      || new Set(options.map(option => option.value)).size !== options.length) invalidWorldCharacterRead();
  }
  const editableKeys = ["personality", "speech_style", "worldview", "character_background", "topic_preferences", "safety_rules",
    "active_hours_start", "active_hours_end", "activity_interval_minutes", "max_posts_per_day", "max_comments_per_day",
    "generation_model", "image_model", "image_style", "appearance_prompt"];
  const editableSettings = Object.fromEntries(editableKeys.filter(key => key in settings).map(key => [key, settings[key]]));
  return { ...payload, settings: editableSettings, capabilities: decodeWorldCharacterCapabilities(payload.capabilities) } as WorldCharacterSettingsRead;
}
