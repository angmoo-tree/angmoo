import type { WorldSurfaceItem } from "@/features/device-home/public";


export type LocalWorldAppRead = {
  schema_version: "local-world-app-v1";
  surface: "world_app";
  world: WorldSurfaceItem;
};

export type OwnerControlledActorRead = {
  schema_version: "owner-controlled-world-character-v1";
  world_character_id: string;
  world_id: string;
  character_id: string;
  control_mode: "owner_controlled";
  status: string;
  autonomous_enabled: false;
  version: number;
  profile: {
    display_name: string;
    avatar_url: string;
    intro: string;
    role_key: string | null;
    preferred_address: string;
    interests: string[];
    background: string;
  };
};

export type ManualSocialPostRead = {
  id: string;
  world_id: string;
  author_world_character_id: string;
  author_name: string;
  title: string;
  body: string;
  post_type: string;
  reply_to_post_id: string | null;
  created_at: string;
  can_owner_reply: boolean;
};

export type ManualSocialFeedRead = {
  schema_version: "owner-manual-social-v1";
  world_id: string;
  owner_world_character_id: string;
  items: ManualSocialPostRead[];
};

export type ManualSocialWriteRead = {
  schema_version: "owner-manual-social-v1";
  operation: "post" | "reply";
  replayed: boolean;
  post: ManualSocialPostRead;
  delivery: {
    provider_call_count: 0;
    inbox_candidate_id: string | null;
    inbox_status: "not_applicable" | "pending";
    public_reaction_required: false;
  };
};

export class WorldAppApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
    this.name = "WorldAppApiError";
  }
}

export async function getLocalWorldApp(
  worldId: string,
  options: { signal?: AbortSignal } = {},
): Promise<LocalWorldAppRead> {
  const response = await fetch(
    `/api/backend/worlds/mine/${encodeURIComponent(worldId)}`,
    {
      cache: "no-store",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      signal: options.signal,
    },
  );
  const payload = (await response.json().catch(() => null)) as unknown;
  if (!response.ok) {
    const detail =
      typeof payload === "object" &&
      payload !== null &&
      "detail" in payload &&
      typeof payload.detail === "string"
        ? payload.detail
        : `http_${response.status}`;
    throw new WorldAppApiError(response.status, detail);
  }
  if (
    typeof payload !== "object" ||
    payload === null ||
    !("schema_version" in payload) ||
    payload.schema_version !== "local-world-app-v1" ||
    !("surface" in payload) ||
    payload.surface !== "world_app" ||
    !("world" in payload) ||
    typeof payload.world !== "object" ||
    payload.world === null ||
    !("world_id" in payload.world) ||
    payload.world.world_id !== worldId ||
    !("launchable" in payload.world) ||
    payload.world.launchable !== true
  ) {
    throw new WorldAppApiError(502, "world_app_schema_mismatch");
  }
  return payload as LocalWorldAppRead;
}

export async function getOwnerControlledActor(
  worldId: string,
  options: { signal?: AbortSignal } = {},
): Promise<OwnerControlledActorRead | null> {
  const response = await fetch(
    `/api/backend/worlds/${encodeURIComponent(worldId)}/owner-character`,
    {
      cache: "no-store",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      signal: options.signal,
    },
  );
  if (response.status === 404) return null;
  const payload = (await response.json().catch(() => null)) as unknown;
  if (!response.ok) {
    const detail =
      typeof payload === "object" &&
      payload !== null &&
      "detail" in payload &&
      typeof payload.detail === "string"
        ? payload.detail
        : `http_${response.status}`;
    throw new WorldAppApiError(response.status, detail);
  }
  if (
    typeof payload !== "object" ||
    payload === null ||
    !("schema_version" in payload) ||
    payload.schema_version !== "owner-controlled-world-character-v1" ||
    !("world_id" in payload) ||
    payload.world_id !== worldId ||
    !("control_mode" in payload) ||
    payload.control_mode !== "owner_controlled" ||
    !("autonomous_enabled" in payload) ||
    payload.autonomous_enabled !== false
  ) {
    throw new WorldAppApiError(502, "owner_actor_schema_mismatch");
  }
  return payload as OwnerControlledActorRead;
}

function detailFromPayload(payload: unknown, status: number): string {
  return typeof payload === "object" &&
    payload !== null &&
    "detail" in payload &&
    typeof payload.detail === "string"
    ? payload.detail
    : `http_${status}`;
}

async function manualSocialRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    cache: "no-store",
    credentials: "same-origin",
    ...options,
    headers: {
      Accept: "application/json",
      ...options.headers,
    },
  });
  const payload = (await response.json().catch(() => null)) as unknown;
  if (!response.ok) {
    throw new WorldAppApiError(
      response.status,
      detailFromPayload(payload, response.status),
    );
  }
  if (
    typeof payload !== "object" ||
    payload === null ||
    !("schema_version" in payload) ||
    payload.schema_version !== "owner-manual-social-v1"
  ) {
    throw new WorldAppApiError(502, "manual_social_schema_mismatch");
  }
  return payload as T;
}

export function getManualSocialFeed(
  worldId: string,
  options: { signal?: AbortSignal } = {},
): Promise<ManualSocialFeedRead> {
  return manualSocialRequest<ManualSocialFeedRead>(
    `/api/backend/worlds/${encodeURIComponent(worldId)}/manual-social/feed`,
    { signal: options.signal },
  );
}

export function createOwnerManualPost(
  worldId: string,
  data: { title: string; body: string },
  idempotencyKey: string,
): Promise<ManualSocialWriteRead> {
  return manualSocialRequest<ManualSocialWriteRead>(
    `/api/backend/worlds/${encodeURIComponent(worldId)}/manual-social/posts`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify(data),
    },
  );
}

export function createOwnerManualReply(
  worldId: string,
  postId: string,
  body: string,
  idempotencyKey: string,
): Promise<ManualSocialWriteRead> {
  return manualSocialRequest<ManualSocialWriteRead>(
    `/api/backend/worlds/${encodeURIComponent(worldId)}/manual-social/posts/${encodeURIComponent(postId)}/replies`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify({ body }),
    },
  );
}
