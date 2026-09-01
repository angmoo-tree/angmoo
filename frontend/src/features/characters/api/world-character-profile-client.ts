import { clearStoredUser, notifyAuthChanged } from "@/shared/auth/public";
import { runtimeFetch } from "@/shared/runtime/public";

import type {
  WorldCharacterProfileListRead,
  WorldCharacterPublicProfile,
} from "../model/world-character-profile-contract";

export class WorldCharacterProfileApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
    this.name = "WorldCharacterProfileApiError";
  }
}

export async function listWorldCharacterProfiles(
  worldId: string,
  options: { signal?: AbortSignal } = {},
): Promise<WorldCharacterProfileListRead> {
  const payload = await requestProfileApi<WorldCharacterProfileListRead>(
    worldCharacterApiPath(worldId),
    options,
  );
  if (
    payload.schema_version !== "world-character-profile-list-v1" ||
    payload.world_id !== worldId ||
    !Array.isArray(payload.items) ||
    payload.items.some((item) => !profileMatchesScope(item, worldId))
  ) {
    throw new WorldCharacterProfileApiError(502, "world_character_profile_scope_mismatch");
  }
  return payload;
}

export async function getWorldCharacterProfile(
  worldId: string,
  worldCharacterId: string,
  options: { signal?: AbortSignal } = {},
): Promise<WorldCharacterPublicProfile> {
  const payload = await requestProfileApi<WorldCharacterPublicProfile>(
    `${worldCharacterApiPath(worldId)}/${encodeURIComponent(worldCharacterId)}`,
    options,
  );
  if (
    !profileMatchesScope(payload, worldId) ||
    payload.world_character_id !== worldCharacterId
  ) {
    throw new WorldCharacterProfileApiError(502, "world_character_profile_scope_mismatch");
  }
  return payload;
}

function worldCharacterApiPath(worldId: string) {
  return `/api/backend/worlds/${encodeURIComponent(worldId)}/world-characters`;
}

async function requestProfileApi<T>(
  path: string,
  options: { signal?: AbortSignal },
): Promise<T> {
  const response = await runtimeFetch(path, {
    cache: "no-store",
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    signal: options.signal,
  });
  const payload = (await response.json().catch(() => null)) as unknown;
  if (!response.ok) {
    if (response.status === 401) {
      clearStoredUser();
      notifyAuthChanged();
    }
    throw new WorldCharacterProfileApiError(
      response.status,
      errorDetail(payload, `http_${response.status}`),
    );
  }
  return payload as T;
}

function profileMatchesScope(
  value: unknown,
  worldId: string,
): value is WorldCharacterPublicProfile {
  if (!value || typeof value !== "object") return false;
  const profile = value as Partial<WorldCharacterPublicProfile>;
  return (
    profile.schema_version === "world-character-profile-v1" &&
    profile.world_id === worldId &&
    typeof profile.world_character_id === "string" &&
    typeof profile.character_id === "string" &&
    typeof profile.display_name === "string" &&
    profile.status === "active" &&
    profile.profile_capability === "available"
  );
}

function errorDetail(payload: unknown, fallback: string) {
  if (
    payload &&
    typeof payload === "object" &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail;
  }
  return fallback;
}
