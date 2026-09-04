import type {
  LocalWorldSurfaceRead,
  WorldSurface,
} from "../types";
import { runtimeFetch } from "@/lib/runtime/runtime-config";


export class DeviceHomeApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
    this.name = "DeviceHomeApiError";
  }
}

export async function getLocalWorldSurface(
  surface: WorldSurface,
  options: { signal?: AbortSignal } = {},
): Promise<LocalWorldSurfaceRead> {
  const response = await runtimeFetch(
    `/api/backend/worlds/mine?surface=${encodeURIComponent(surface)}`,
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
    throw new DeviceHomeApiError(response.status, detail);
  }
  if (
    typeof payload !== "object" ||
    payload === null ||
    !("schema_version" in payload) ||
    payload.schema_version !== "local-world-surface-v1" ||
    !("surface" in payload) ||
    payload.surface !== surface ||
    !("items" in payload) ||
    !Array.isArray(payload.items)
  ) {
    throw new DeviceHomeApiError(502, "world_surface_schema_mismatch");
  }
  return payload as LocalWorldSurfaceRead;
}
