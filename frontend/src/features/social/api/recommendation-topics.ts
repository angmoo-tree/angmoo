import { requestSocialApi } from "@/lib/http/social-request";

export type RecommendationTopics = {
  world_id: string;
  world_character_id: string | null;
  state: "pending" | "running" | "ready" | "failed" | "stale";
  topics: { id: string; name: string; scope: "common" | "world" }[];
  key_world_character_id: string | null;
  model: string;
  thinking_level: string;
  last_code: string | null;
  approval_required: boolean;
  recent_feed: { post_id: string; title: string; sources: string[]; lane: string | null; outcome: string | null; action: string | null }[];
};

function path(worldId: string, suffix = "", characterId?: string) {
  return `/worlds/${encodeURIComponent(worldId)}/recommendation-topics${suffix}${characterId ? `?world_character_id=${encodeURIComponent(characterId)}` : ""}`;
}

export const readRecommendationTopics = (worldId: string, characterId?: string, signal?: AbortSignal) =>
  requestSocialApi<RecommendationTopics>(path(worldId, "", characterId), { signal });

export const regenerateRecommendationTopics = (worldId: string, requestId: string, characterId?: string) =>
  requestSocialApi<RecommendationTopics>(path(worldId, "/regenerate", characterId), { method: "POST", body: { request_id: requestId } });

export const connectRecommendationKey = (worldId: string, characterId: string | null) =>
  requestSocialApi<RecommendationTopics>(path(worldId, "/key"), { method: "PUT", body: { world_character_id: characterId } });
