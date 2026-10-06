import { apiRequest } from "@/lib/http/api-request";
import { invalidWorldCharacterRead, isNonNegativeInteger, isNullableString, isRecord, worldCharacterManagementApiPath } from "./world-character-dashboard-client";

export type WorldCharacterStatus = {
  contract_version: "world-character-status-v1"; world_id: string; world_character_id: string; revision: number;
  autonomous_enabled: boolean; state: { state: "user" | "off" | "running" | "outside_hours" | "error" | "waiting" | "capacity_wait" | "not_ready"; reason: string | null }; timezone: string; next_activity_at: string | null;
  recent_activity: { id: string; action: string; status: string; occurred_at: string; post_id: string | null; title: string | null }[];
  persona: Record<"worldview" | "personality" | "speech_style" | "character_background" | "topic_preferences" | "safety_rules", string>;
  summary: { posts: number; replies: number; likes: number; post_limit: number; reply_limit: number; active_hours: string; allowed_actions: string[] };
};

export async function getWorldCharacterStatus(worldId: string, actorId: string, signal: AbortSignal): Promise<WorldCharacterStatus> {
  const value = await apiRequest<unknown>(`${worldCharacterManagementApiPath(worldId, actorId)}/status`, { signal });
  if (!isRecord(value) || value.contract_version !== "world-character-status-v1" || value.world_id !== worldId || value.world_character_id !== actorId
    || !isNonNegativeInteger(value.revision) || typeof value.autonomous_enabled !== "boolean" || !isRecord(value.state)
    || !["user", "off", "running", "outside_hours", "error", "waiting", "capacity_wait", "not_ready"].includes(String(value.state.state)) || !isNullableString(value.state.reason) || typeof value.timezone !== "string"
    || !isNullableString(value.next_activity_at) || !isRecord(value.persona) || !isRecord(value.summary) || !Array.isArray(value.recent_activity) || value.recent_activity.length > 20) invalidWorldCharacterRead();
  const persona = value.persona, summary = value.summary;
  if (!["worldview", "personality", "speech_style", "character_background", "topic_preferences", "safety_rules"].every(key => typeof persona[key] === "string")
    || !["posts", "replies", "likes", "post_limit", "reply_limit"].every(key => isNonNegativeInteger(summary[key])) || typeof summary.active_hours !== "string"
    || !Array.isArray(summary.allowed_actions) || !summary.allowed_actions.every(action => ["reply", "post", "like"].includes(action))
    || !value.recent_activity.every(row => isRecord(row) && ["id", "action", "status", "occurred_at"].every(key => typeof row[key] === "string")
      && typeof row.occurred_at === "string" && Number.isFinite(Date.parse(row.occurred_at)) && isNullableString(row.post_id) && isNullableString(row.title))) invalidWorldCharacterRead();
  return value as WorldCharacterStatus;
}
