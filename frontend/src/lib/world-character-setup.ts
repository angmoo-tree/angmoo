import { runtimeFetch } from "@/shared/runtime/public";

export type WorldSetupStage = "community_profile" | "repertoire" | "approval";
export type WorldSetupState =
  | "ready"
  | "needs_profile"
  | "needs_repertoire"
  | "stale"
  | "failed"
  | "running";
export type WorldActivityDaypart =
  | "dawn"
  | "morning"
  | "afternoon"
  | "evening";

export type WorldCommunityActionPreference = {
  weight: number;
  note: string;
};

export type WorldCommunityProfileRead = {
  id: string;
  world_character_id: string;
  status: string;
  visible_summary: string;
  core_interests: string[];
  adjacent_interests: string[];
  avoid_topics: string[];
  discovery_openness: number;
  search_keywords: string[];
  action_profile: Record<string, WorldCommunityActionPreference>;
  provider: string;
  model: string;
  generated_at: string;
  approved_at: string | null;
};

export type WorldActivityCandidateRead = {
  id: string;
  repertoire_id: string;
  ordinal: number;
  daypart: WorldActivityDaypart;
  activity_kind:
    | "duty"
    | "rest"
    | "self_care"
    | "hobby"
    | "exploration"
    | "social"
    | "maintenance"
    | "challenge";
  title: string;
  activity_seed: string;
  place_key: string | null;
  social_mode: "solo" | "open_to_interaction" | "cooperative";
  canonical_signature: string;
  enabled: boolean;
};

export type WorldActivityRepertoireRead = {
  id: string;
  world_character_id: string;
  status: string;
  provider: string;
  model: string;
  generated_at: string;
  approved_at: string | null;
  candidates: WorldActivityCandidateRead[];
};

export type WorldCharacterSetupRead = {
  world_character_id: string;
  world_id: string;
  character_id: string;
  state: WorldSetupState;
  autonomy_ready: boolean;
  autonomous_enabled: boolean;
  reused: boolean;
  can_retry_stage: WorldSetupStage | null;
  can_approve: boolean;
  can_regenerate: boolean;
  safe_reason_code: string | null;
  current_character_contract_hash: string;
  current_world_contract_hash: string;
  generated_character_contract_hash: string | null;
  generated_world_contract_hash: string | null;
  profile: WorldCommunityProfileRead | null;
  repertoire: WorldActivityRepertoireRead | null;
};

export type WorldCharacterSetupPreflightRead = {
  world_character_id: string;
  world_id: string;
  character_id: string;
  provider: string | null;
  model: string | null;
  credential_ready: boolean;
  logical_call_count: number;
  physical_request_count: number;
  profile_max_output_tokens: number;
  repertoire_max_output_tokens: number;
  regeneration_limit_character_24h: number;
  regeneration_limit_owner_24h: number;
  reused: boolean;
  safe_reason_code: string | null;
};

export type WorldCharacterEntryRead = {
  id: string;
  world_id: string;
  character_id: string;
  membership_id: string;
  role_key: string | null;
  status: string;
  autonomous_enabled: boolean;
  version: number;
  reused: boolean;
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
  feed_runtime_mode: "legacy_latest_v1" | "keyword_search_v1";
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

type RequestOptions = Omit<RequestInit, "body"> & { body?: unknown };

export class WorldCharacterSetupApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail: unknown,
  ) {
    super(message);
    this.name = "WorldCharacterSetupApiError";
  }
}

async function apiRequest<T>(path: string, options: RequestOptions = {}) {
  const { body, headers, ...rest } = options;
  const response = await runtimeFetch(`/api/backend${path}`, {
    ...rest,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      ...(headers ?? {}),
    },
  });
  const text = await response.text();
  let payload: unknown = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload
        ? (payload as { detail: unknown }).detail
        : null;
    const code =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? "request_validation_error"
          : `http_${response.status}`;
    throw new WorldCharacterSetupApiError(code, response.status, detail);
  }
  return payload as T;
}

function setupPath(worldCharacterId: string, suffix = "") {
  return `/world-characters/${encodeURIComponent(worldCharacterId)}/autonomy-setup${suffix}`;
}

export function enterWorldWithCharacter(
  worldId: string,
  data: {
    character_id: string;
    role_key: string | null;
    local_background: string;
    idempotency_key: string;
  },
) {
  return apiRequest<WorldCharacterEntryRead>(
    `/worlds/${encodeURIComponent(worldId)}/characters`,
    { method: "POST", body: data },
  );
}

export async function getExistingWorldCharacterEntry(
  worldId: string,
  characterId: string,
) {
  try {
    return await apiRequest<WorldCharacterEntryRead>(
      `/worlds/${encodeURIComponent(worldId)}/characters/${encodeURIComponent(characterId)}`,
    );
  } catch (error) {
    if (error instanceof WorldCharacterSetupApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export function getWorldCharacterSetup(worldCharacterId: string) {
  return apiRequest<WorldCharacterSetupRead>(setupPath(worldCharacterId));
}

export function getWorldFeedStatus(worldCharacterId: string) {
  return apiRequest<WorldFeedCycleStatusRead>(
    `/world-characters/${encodeURIComponent(worldCharacterId)}/feed-status`,
  );
}

export function preflightWorldCharacterSetup(worldCharacterId: string) {
  return apiRequest<WorldCharacterSetupPreflightRead>(
    setupPath(worldCharacterId, "/preflight"),
    { method: "POST" },
  );
}

export function generateWorldCharacterSetup(
  worldCharacterId: string,
  idempotencyKey: string,
) {
  return apiRequest<WorldCharacterSetupRead>(
    setupPath(worldCharacterId, "/generate"),
    {
      method: "POST",
      body: {
        idempotency_key: idempotencyKey,
        consent_policy_version: "world-character-setup-v1",
        consented: true,
      },
    },
  );
}

export function retryWorldCharacterSetup(
  worldCharacterId: string,
  stage: "community_profile" | "repertoire",
  idempotencyKey: string,
) {
  return apiRequest<WorldCharacterSetupRead>(
    setupPath(worldCharacterId, "/retry"),
    {
      method: "POST",
      body: {
        idempotency_key: idempotencyKey,
        consent_policy_version: "world-character-setup-v1",
        consented: true,
        stage,
      },
    },
  );
}

export function approveWorldCharacterSetup(
  worldCharacterId: string,
  profileId: string,
  repertoireId: string,
  idempotencyKey: string,
) {
  return apiRequest<WorldCharacterSetupRead>(
    setupPath(worldCharacterId, "/approve"),
    {
      method: "POST",
      body: {
        idempotency_key: idempotencyKey,
        profile_id: profileId,
        repertoire_id: repertoireId,
      },
    },
  );
}

export function rejectWorldCharacterSetup(
  worldCharacterId: string,
  reason: string,
  idempotencyKey: string,
) {
  return apiRequest<WorldCharacterSetupRead>(
    setupPath(worldCharacterId, "/reject"),
    {
      method: "POST",
      body: { idempotency_key: idempotencyKey, reason },
    },
  );
}
