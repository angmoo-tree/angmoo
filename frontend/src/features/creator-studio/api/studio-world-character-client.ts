import type {
  StudioCharacterCandidateListRead,
  StudioWorldCharacterListRead,
  WorldCharacterEntryRead,
  WorldCharacterLeaveRead,
} from "../model/studio-world-character-contract";
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

async function readPayload(response: Response): Promise<unknown> {
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
  return payload;
}

export async function getStudioCharacterCandidates(
  worldId: string,
  options: { signal?: AbortSignal } = {},
): Promise<StudioCharacterCandidateListRead> {
  const response = await runtimeFetch(
    `/api/backend/worlds/${encodeURIComponent(worldId)}/character-candidates`,
    {
      cache: "no-store",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      signal: options.signal,
    },
  );
  const payload = await readPayload(response);
  if (
    typeof payload !== "object" ||
    payload === null ||
    !("schema_version" in payload) ||
    payload.schema_version !== "studio-character-candidates-v1" ||
    !("world_id" in payload) ||
    payload.world_id !== worldId ||
    !("items" in payload) ||
    !Array.isArray(payload.items)
  ) {
    throw new StudioWorldCharacterApiError(502, "studio_character_candidate_schema_mismatch");
  }
  return payload as StudioCharacterCandidateListRead;
}

export async function enterStudioWorldCharacter(
  worldId: string,
  data: {
    character_id: string;
    role_key: string;
    local_background?: string;
    idempotency_key: string;
  },
): Promise<WorldCharacterEntryRead> {
  const response = await runtimeFetch(
    `/api/backend/worlds/${encodeURIComponent(worldId)}/characters`,
    {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    },
  );
  return (await readPayload(response)) as WorldCharacterEntryRead;
}

export async function stopStudioCharacter(characterId: string): Promise<void> {
  const response = await runtimeFetch(
    `/api/backend/agents/${encodeURIComponent(characterId)}/deactivate`,
    {
      method: "POST",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    },
  );
  await readPayload(response);
}

export async function leaveStudioWorldCharacter(
  worldId: string,
  characterId: string,
  data: {
    world_character_id: string;
    version: number;
    confirmation_name: string;
    idempotency_key: string;
  },
): Promise<WorldCharacterLeaveRead> {
  const response = await runtimeFetch(
    `/api/backend/worlds/${encodeURIComponent(worldId)}/characters/${encodeURIComponent(characterId)}/leave`,
    {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    },
  );
  return (await readPayload(response)) as WorldCharacterLeaveRead;
}
