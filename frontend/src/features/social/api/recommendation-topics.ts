import type { FeedStatus } from "@/features/social/api/feed-status";
import { requestSocialApi } from "@/lib/http/social-request";

export type DeliveryPost = {
  post_id: string;
  title: string;
  sources: ("latest" | "interest" | "relation" | "explore")[];
  lane: "latest" | "interest" | "relation" | "explore" | null;
  selected_action: "like" | "comment" | "repost" | "follow" | null;
  result_state: "unrecorded" | "no_action" | "not_selected" | "selected" | "pending" | "succeeded" | "failed" | "not_performed";
};

export type RecommendationDelivery = {
  delivery_id: string;
  recorded_at: string;
  recorded_post_count: number | null;
  visible_post_count: number;
  unavailable_post_count: number | null;
  is_partial: boolean;
  posts: DeliveryPost[];
};

export type RecommendationTopics = {
  feed_status?: FeedStatus | null;
  world_id: string;
  world_character_id: string | null;
  state: "pending" | "running" | "ready" | "failed" | "stale";
  topics: { id: string; name: string; scope: "common" | "world" }[];
  key_world_character_id: string | null;
  model: string;
  thinking_level: string;
  last_code: string | null;
  approval_required: boolean;
  recent_deliveries?: RecommendationDelivery[];
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
