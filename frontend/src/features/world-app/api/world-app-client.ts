import type { WorldSurfaceItem } from "@/features/device-home/public";


export type LocalWorldAppRead = {
  schema_version: "local-world-app-v1";
  surface: "world_app";
  world: WorldSurfaceItem;
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
