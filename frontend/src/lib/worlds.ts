export type WorldDaypart = "dawn" | "morning" | "afternoon" | "evening";
export type WorldVisibility = "private" | "unlisted" | "public";
export type WorldJoinPolicy =
  | "open"
  | "approval_required"
  | "invite_only"
  | "private";

export type WorldPlaceInput = {
  key: string;
  name: string;
  description: string;
  available_dayparts: WorldDaypart[];
  access_role_keys: string[];
};

export type WorldRoleInput = {
  key: string;
  name: string;
  description: string;
  responsibilities: string[];
  allowed_activity_scope: string[];
  autonomous_allowed: boolean;
};

export type WorldDaypartProfileInput = {
  daypart: WorldDaypart;
  description: string;
  available_features: string[];
  restricted_features: string[];
};

export type WorldRuleInput = {
  key: string;
  rule_kind: "allow" | "forbid";
  description: string;
};

export type WorldGlossaryTermInput = {
  key: string;
  term: string;
  meaning: string;
};

export type WorldDefinition = {
  name: string;
  tagline: string;
  setting_description: string;
  daily_life_description: string;
  genre_tags: string[];
  tone_tags: string[];
  timezone: string;
  language: string;
  visibility: WorldVisibility;
  join_policy: WorldJoinPolicy;
  additional_generation_guidance: string;
  places: WorldPlaceInput[];
  roles: WorldRoleInput[];
  daypart_profiles: WorldDaypartProfileInput[];
  rules: WorldRuleInput[];
  glossary: WorldGlossaryTermInput[];
};

export type WorldRead = WorldDefinition & {
  id: string;
  slug: string;
  banner_media_id: string | null;
  banner_alt_text: string;
  status: "draft" | "published" | "archived";
  definition_version: number;
  row_version: number;
  contract_version: string;
  contract_hash: string;
  readiness_status: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
};

export type WorldValidationIssue = {
  reason_code: string;
  field: string | null;
  message: string;
};

export type WorldReadiness = {
  world_id: string;
  definition_version: number;
  row_version: number;
  contract_version: string;
  contract_hash: string;
  required_fields: Record<string, boolean>;
  optional_setting_count: number;
  quality_tier: "CORE" | "ENRICHED" | "DETAILED";
  issues: WorldValidationIssue[];
  ready_for_publish: boolean;
  evaluated_at: string;
};

export type WorldCreatorContext = {
  world: WorldRead;
  membership_role: "owner" | "editor";
  readiness: WorldReadiness;
};

export type WorldGenerationContext = Omit<
  WorldDefinition,
  "visibility" | "join_policy"
> & {
  world_id: string;
  definition_version: number;
  contract_version: string;
  contract_hash: string;
};

export type WorldDraftCreate = WorldDefinition & {
  idempotency_key: string;
};

export type WorldUpdate = Partial<WorldDefinition> & {
  row_version: number;
};

type RequestOptions = Omit<RequestInit, "body"> & { body?: unknown };

export class WorldApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail: unknown,
  ) {
    super(message);
    this.name = "WorldApiError";
  }
}

type FastApiValidationIssue = { loc?: unknown; msg?: unknown };

function isFastApiValidationIssue(value: unknown): value is FastApiValidationIssue {
  return typeof value === "object" && value !== null;
}

export function requestValidationFields(detail: unknown) {
  if (!Array.isArray(detail)) return [];
  return Array.from(
    new Set(
      detail.flatMap((issue) => {
        if (!isFastApiValidationIssue(issue) || !Array.isArray(issue.loc)) return [];
        const path = issue.loc
          .filter((item) => item !== "body")
          .map(String)
          .join(".");
        return path ? [path] : [];
      }),
    ),
  );
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
        : typeof detail === "object" &&
            detail !== null &&
            "code" in detail &&
            typeof (detail as { code?: unknown }).code === "string"
          ? (detail as { code: string }).code
          : Array.isArray(detail)
            ? "request_validation_error"
            : `http_${response.status}`;
    throw new WorldApiError(code, response.status, detail);
  }
  return payload as T;
}

function worldPath(worldId: string, suffix = "") {
  return `/worlds/${encodeURIComponent(worldId)}${suffix}`;
}

export function createWorld(data: WorldDraftCreate) {
  return apiRequest<WorldCreatorContext>("/worlds", {
    method: "POST",
    body: data,
  });
}

export function getWorldCreatorContext(worldId: string) {
  return apiRequest<WorldCreatorContext>(worldPath(worldId, "/creator-context"));
}

export function updateWorld(worldId: string, data: WorldUpdate) {
  return apiRequest<WorldCreatorContext>(worldPath(worldId), {
    method: "PATCH",
    body: data,
  });
}

export function validateWorld(worldId: string) {
  return apiRequest<WorldReadiness>(worldPath(worldId, "/validate"), {
    method: "POST",
  });
}

export function publishWorld(worldId: string, rowVersion: number) {
  return apiRequest<WorldCreatorContext>(worldPath(worldId, "/publish"), {
    method: "POST",
    body: { row_version: rowVersion },
  });
}

export function archiveWorld(worldId: string, rowVersion: number) {
  return apiRequest<WorldCreatorContext>(worldPath(worldId, "/archive"), {
    method: "POST",
    body: { row_version: rowVersion },
  });
}

export function uploadWorldBanner(
  worldId: string,
  data: {
    row_version: number;
    content_type: string;
    data_base64: string;
    alt_text: string;
  },
) {
  return apiRequest<WorldCreatorContext>(worldPath(worldId, "/banner"), {
    method: "POST",
    body: data,
  });
}

export function removeWorldBanner(worldId: string, rowVersion: number) {
  return apiRequest<WorldCreatorContext>(worldPath(worldId, "/banner"), {
    method: "DELETE",
    body: { row_version: rowVersion },
  });
}

export function getWorldGenerationContext(worldId: string) {
  return apiRequest<WorldGenerationContext>(
    worldPath(worldId, "/generation-context"),
  );
}
