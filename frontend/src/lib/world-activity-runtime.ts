export type ActivityDaypart = "dawn" | "morning" | "afternoon" | "evening";
export type ActivityRuntimeMode = "legacy_resident_v1" | "routine_resident_v1";

export type ActivityEpisodeRead = {
  id: string;
  plan_item_id: string;
  status: "planned" | "active" | "completed" | "interrupted" | "cancelled";
  current_state_schema_version: number;
  current_state_snapshot: Record<string, unknown>;
  last_successful_beat_id: string | null;
  last_successful_post_id: string | null;
  last_successful_sequence_no: number | null;
  last_successful_beat_at: string | null;
  considered_event_count: number;
  used_event_count: number;
  overflow_event_count: number;
  recent_outcome: string | null;
  next_sequence_no: number;
  started_at: string | null;
  completed_at: string | null;
  terminal_reason_code: string | null;
};

export type DailyActivityPlanItemRead = {
  id: string;
  daypart: ActivityDaypart;
  selected_candidate_id: string | null;
  candidate_signature: string | null;
  candidate_ordinal: number | null;
  origin_type: "repertoire" | "joint_activity";
  supersedes_plan_item_id: string | null;
  is_user_pinned: boolean;
  activity_kind: string;
  title: string;
  activity_seed: string;
  social_mode: string;
  place_key: string | null;
  joint_activity_id: string | null;
  scheduled_start_at: string;
  scheduled_end_at: string;
  status: "planned" | "active" | "completed" | "skipped" | "interrupted" | "cancelled";
  revision_count: number;
  terminal_reason_code: string | null;
  episode: ActivityEpisodeRead | null;
};

export type DailyActivityPlanRead = {
  id: string;
  world_id: string;
  world_character_id: string;
  local_date: string;
  timezone_name: string;
  timezone_contract_version: string;
  repertoire_id: string;
  world_definition_hash: string;
  character_definition_hash: string;
  repertoire_contract_version: string;
  selection_contract_version: string;
  selection_seed_hash: string;
  status: "planned" | "active" | "completed" | "interrupted" | "cancelled";
  revision_count: number;
  version: number;
  autonomous_enabled: boolean;
  activity_runtime_mode: ActivityRuntimeMode;
  current_daypart: ActivityDaypart | null;
  reused: boolean;
  items: DailyActivityPlanItemRead[];
};

export type SocialEventEvidenceRead = {
  evidence_kind: string;
  source_object_type: string;
  source_object_id: string;
  root_post_id: string | null;
  source_post_id: string | null;
  target_post_id: string | null;
  source_status: "available" | "excluded";
  exclusion_reason: string | null;
};

export type SocialEventRead = {
  id: string;
  world_id: string;
  actor_world_character_id: string;
  target_world_character_id: string | null;
  event_type: string;
  occurred_at: string;
  retrieval_status: string;
  evidence: SocialEventEvidenceRead[];
};

export type RelationshipStateRead = {
  id: string;
  actor_world_character_id: string;
  target_world_character_id: string;
  familiarity: number;
  affinity: number;
  trust: number;
  tension: number;
  interaction_count: number;
  last_event_id: string | null;
  last_event_at: string | null;
  version: number;
};

export type ActivityProposalRead = {
  id: string;
  proposer_world_character_id: string;
  target_world_character_id: string;
  activity_seed: string;
  place_key: string | null;
  target_daypart: ActivityDaypart;
  date_policy: "exact" | "earliest_available";
  target_date: string | null;
  status: string;
  expires_at: string;
};

export type JointActivityParticipantRead = {
  world_character_id: string;
  role: "proposer" | "acceptor";
  participation_status: string;
  linked_daily_activity_plan_item_id: string | null;
  linked_activity_episode_id: string | null;
  represented_at: string | null;
  last_joint_post_id: string | null;
};

export type JointActivityRead = {
  id: string;
  proposal_id: string | null;
  activity_seed: string;
  place_key: string | null;
  scheduled_local_date: string | null;
  target_daypart: ActivityDaypart | null;
  timezone_snapshot: string | null;
  status: string;
  opening_post_id: string | null;
  opened_by_world_character_id: string | null;
  started_at: string | null;
  completed_at: string | null;
  participants: JointActivityParticipantRead[];
};

export type SocialMemoryDiagnosticsRead = {
  world_id: string;
  world_character_id: string;
  recent_events: SocialEventRead[];
  outgoing_relationships: RelationshipStateRead[];
  incoming_relationships: RelationshipStateRead[];
  open_proposals: ActivityProposalRead[];
  active_joint_activities: JointActivityRead[];
  graph_outbox_pending_count: number;
  graph_outbox_processing_count: number;
  graph_outbox_dead_count: number;
  graph_oldest_pending_age_seconds: number | null;
  graph_last_succeeded_at: string | null;
  relationship_graph_status:
    | "disabled"
    | "healthy"
    | "lagging"
    | "rebuilding"
    | "unavailable"
    | "timeout"
    | "misconfigured";
  latest_relationship_version_parity: boolean | null;
  graph_replay_active: boolean;
};
type RequestOptions = Omit<RequestInit, "body"> & { body?: unknown };

export class DailyActivityPlanApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail: unknown,
  ) {
    super(message);
    this.name = "DailyActivityPlanApiError";
  }
}

async function apiRequest<T>(path: string, options: RequestOptions = {}) {
  const { body, headers, ...rest } = options;
  const response = await fetch(`/api/backend${path}`, {
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
    throw new DailyActivityPlanApiError(code, response.status, detail);
  }
  return payload as T;
}

function planPath(characterId: string, worldId: string, suffix = "") {
  return `/characters/${encodeURIComponent(characterId)}/worlds/${encodeURIComponent(worldId)}/activity-plan${suffix}`;
}

export async function getDailyActivityPlan(characterId: string, worldId: string) {
  try {
    return await apiRequest<DailyActivityPlanRead>(planPath(characterId, worldId));
  } catch (error) {
    if (error instanceof DailyActivityPlanApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export function prepareDailyActivityPlan(
  characterId: string,
  worldId: string,
  idempotencyKey: string,
) {
  return apiRequest<DailyActivityPlanRead>(planPath(characterId, worldId, "/prepare"), {
    method: "POST",
    body: { idempotency_key: idempotencyKey },
  });
}

export function getSocialMemoryDiagnostics(characterId: string, worldId: string) {
  return apiRequest<SocialMemoryDiagnosticsRead>(
    `/characters/${encodeURIComponent(characterId)}/worlds/${encodeURIComponent(worldId)}/social-memory`,
  );
}


export function updateActivityRuntimeMode(
  characterId: string,
  worldId: string,
  activityRuntimeMode: ActivityRuntimeMode,
) {
  return apiRequest<{
    world_character_id: string;
    world_id: string;
    character_id: string;
    activity_runtime_mode: ActivityRuntimeMode;
    autonomous_enabled: boolean;
  }>(
    `/characters/${encodeURIComponent(characterId)}/worlds/${encodeURIComponent(worldId)}/activity-runtime-mode`,
    {
      method: "PATCH",
      body: { activity_runtime_mode: activityRuntimeMode },
    },
  );
}
