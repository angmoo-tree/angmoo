import { requestSocialApi } from "@/lib/http/social-request";

export type FeedStatus = {
  readiness: {
    state: "ready" | "blocked" | "disabled" | "unsupported";
    reason_code: string | null;
    persona_changed: boolean;
    checked_at: string;
  };
  last_attempt: {
    run_id: string; occurred_at: string; result: string; reason_code: string | null;
    candidate_count: number | null; delivered_count: number | null;
    delivery_state: "prepared" | "dispatched" | "uncertain" | "delivered" | null;
  } | null;
};

export type WorldFeedAction = "like" | "comment" | "repost" | "follow";

export type WorldFeedObservationRead = {
  observation_id: string;
  post_id: string;
  post_title: string;
  author_name: string;
  post_created_at: string;
  status: "claimed" | "observed" | "retryable_failed";
  decision_outcome: "not_selected" | "action_selected" | "no_action" | null;
  selected_action: WorldFeedAction | null;
  interaction_intent:
    | "ordinary_comment"
    | "joint_activity_proposal"
    | "proposal_response"
    | null;
  comment_purpose: string | null;
  reason_code: string | null;
  matched_keywords: string[];
  matched_fields: string[];
  rank_score: number;
  observed_at: string | null;
};

export type WorldFeedCycleStatusRead = {
  world_id: string;
  world_character_id: string;
  feed_runtime_mode: "legacy_latest_v1" | "keyword_search_v1" | "topic_recommendation_v1";
  feed_status?: FeedStatus | null;
  runtime_state:
    | "routine_only_legacy_feed"
    | "three_lane_ready"
    | "imported_locked"
    | "autonomy_disabled"
    | "feed_search_degraded"
    | "feed_setup_blocked";
  profile_keyword_count: number;
  profile_keywords_ready: boolean;
  next_keywords: string[];
  next_keyword_offset: number;
  last_cycle_key: string | null;
  last_cycle_at: string | null;
  last_run_id: string | null;
  last_cycle_summary: Record<string, unknown> | null;
  recent_observations: WorldFeedObservationRead[];
};


export function getWorldFeedStatus(worldCharacterId: string) {
  return requestSocialApi<WorldFeedCycleStatusRead>(
    `/world-characters/${encodeURIComponent(worldCharacterId)}/feed-status`,
  );
}
