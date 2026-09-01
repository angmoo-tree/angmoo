import { clearStoredUser, notifyAuthChanged } from "@/shared/auth/public";
import { RuntimeFetchError, runtimeFetch } from "@/shared/runtime/public";

import type {
  WorldCharacterSocialProfilePost,
  WorldCharacterSocialProfileRead,
  WorldCharacterSocialProfileTab,
} from "../model/world-character-social-profile-contract";

export class WorldCharacterSocialProfileApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
    readonly retryable = false,
  ) {
    super(detail);
    this.name = "WorldCharacterSocialProfileApiError";
  }
}

export async function getWorldCharacterSocialProfile(
  worldId: string,
  worldCharacterId: string,
  tab: WorldCharacterSocialProfileTab,
  options: { cursor?: string | null; limit?: number; signal?: AbortSignal } = {},
): Promise<WorldCharacterSocialProfileRead> {
  const query = new URLSearchParams({
    tab,
    limit: String(options.limit ?? 10),
  });
  if (options.cursor) query.set("cursor", options.cursor);

  let response: Response;
  try {
    response = await runtimeFetch(
      `/api/backend/worlds/${encodeURIComponent(worldId)}/world-characters/${encodeURIComponent(worldCharacterId)}/social-profile?${query.toString()}`,
      {
        cache: "no-store",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        signal: options.signal,
      },
    );
  } catch (reason) {
    if (reason instanceof RuntimeFetchError) {
      throw new WorldCharacterSocialProfileApiError(503, reason.code, true);
    }
    throw reason;
  }

  const payload = (await response.json().catch(() => null)) as unknown;
  if (!response.ok) {
    if (response.status === 401) {
      clearStoredUser();
      notifyAuthChanged();
    }
    throw new WorldCharacterSocialProfileApiError(
      response.status,
      errorDetail(payload, `http_${response.status}`),
      response.status >= 500,
    );
  }
  if (!matchesProfileScope(payload, worldId, worldCharacterId, tab)) {
    throw new WorldCharacterSocialProfileApiError(
      502,
      "world_character_social_profile_scope_mismatch",
      true,
    );
  }
  return payload;
}

function matchesProfileScope(
  value: unknown,
  worldId: string,
  worldCharacterId: string,
  tab: WorldCharacterSocialProfileTab,
): value is WorldCharacterSocialProfileRead {
  if (!value || typeof value !== "object") return false;
  const read = value as Partial<WorldCharacterSocialProfileRead>;
  return (
    read.schema_version === "world-character-social-profile-v1" &&
    read.world_id === worldId &&
    read.world_character_id === worldCharacterId &&
    typeof read.character_id === "string" &&
    read.tab === tab &&
    validCounts(read.counts) &&
    Array.isArray(read.items) &&
    read.items.every((item) => validPost(item, worldId, worldCharacterId, tab)) &&
    (read.next_cursor === null || typeof read.next_cursor === "string")
  );
}

function validCounts(value: unknown) {
  if (!value || typeof value !== "object") return false;
  const counts = value as Record<string, unknown>;
  return [
    counts.post_count,
    counts.reply_count,
    counts.liked_post_count,
    counts.received_like_count,
  ].every((count) => Number.isInteger(count) && Number(count) >= 0);
}

function validPost(
  value: unknown,
  worldId: string,
  worldCharacterId: string,
  tab: WorldCharacterSocialProfileTab,
): value is WorldCharacterSocialProfilePost {
  if (!value || typeof value !== "object") return false;
  const post = value as Partial<WorldCharacterSocialProfilePost>;
  const targetMustAuthor = tab === "posts" || tab === "replies";
  return (
    post.world_id === worldId &&
    typeof post.id === "string" &&
    typeof post.author_world_character_id === "string" &&
    (!targetMustAuthor || post.author_world_character_id === worldCharacterId) &&
    typeof post.author_name === "string" &&
    typeof post.title === "string" &&
    typeof post.body === "string" &&
    typeof post.created_at === "string" &&
    Number.isInteger(post.reply_count) &&
    Number(post.reply_count) >= 0 &&
    Number.isInteger(post.like_count) &&
    Number(post.like_count) >= 0 &&
    (post.author_profile_capability === "available" ||
      post.author_profile_capability === "unavailable") &&
    Array.isArray(post.mentioned_characters) &&
    Array.isArray(post.media) &&
    post.media.every(
      (media) =>
        typeof media.url === "string" &&
        media.url.startsWith("/media/") &&
        !media.url.startsWith("//"),
    )
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
