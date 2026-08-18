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
