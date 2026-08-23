import type { StudioWorldCharacterListRead } from "../model/studio-world-character-contract";
import { runtimeFetch } from "@/shared/runtime/public";


export class StudioWorldCharacterApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
    this.name = "StudioWorldCharacterApiError";
  }
}

export async function getStudioWorldCharacters(
  worldId: string,
  options: { signal?: AbortSignal } = {},
): Promise<StudioWorldCharacterListRead> {
  const response = await runtimeFetch(
    `/api/backend/worlds/${encodeURIComponent(worldId)}/characters?surface=studio`,
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
    throw new StudioWorldCharacterApiError(response.status, detail);
  }
  if (
    typeof payload !== "object" ||
    payload === null ||
    !("schema_version" in payload) ||
    payload.schema_version !== "studio-world-character-list-v1" ||
    !("world_id" in payload) ||
    payload.world_id !== worldId ||
    !("items" in payload) ||
    !Array.isArray(payload.items)
  ) {
    throw new StudioWorldCharacterApiError(502, "studio_world_character_schema_mismatch");
  }
  return payload as StudioWorldCharacterListRead;
}
