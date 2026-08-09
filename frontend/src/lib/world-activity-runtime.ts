export type ActivityDaypart = "dawn" | "morning" | "afternoon" | "evening";

export type ActivityEpisodeRead = {
  id: string;
  plan_item_id: string;
  status: "planned" | "active" | "completed" | "interrupted" | "cancelled";
  current_state_schema_version: number;
  current_state_snapshot: Record<string, unknown>;
  last_successful_beat_id: string | null;
  last_successful_beat_at: string | null;
  next_sequence_no: number;
  started_at: string | null;
  completed_at: string | null;
  terminal_reason_code: string | null;
};

export type DailyActivityPlanItemRead = {
  id: string;
  daypart: ActivityDaypart;
  selected_candidate_id: string;
  candidate_signature: string;
  candidate_ordinal: number;
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
  current_daypart: ActivityDaypart | null;
  reused: boolean;
  items: DailyActivityPlanItemRead[];
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
