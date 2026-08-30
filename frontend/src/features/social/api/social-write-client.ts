import {
  RuntimeFetchError,
  runtimeFetch,
} from "@/shared/runtime/public";

import type {
  ManualSocialFeedRead,
  ManualSocialWriteRead,
} from "../model/social-write-contract";

type ManualSocialReadOptions = {
  ownerWorldCharacterId?: string;
  signal?: AbortSignal;
};

export class SocialWriteApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
    readonly retryable = false,
  ) {
    super(detail);
    this.name = "SocialWriteApiError";
  }
}

function detailFromPayload(payload: unknown, status: number): string {
  return typeof payload === "object" &&
    payload !== null &&
    "detail" in payload &&
    typeof payload.detail === "string"
    ? payload.detail
    : `http_${status}`;
}

async function socialWriteRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await runtimeFetch(path, {
      cache: "no-store",
      credentials: "same-origin",
      ...options,
      headers: { Accept: "application/json", ...options.headers },
    });
  } catch (reason) {
    if (reason instanceof RuntimeFetchError) {
      throw new SocialWriteApiError(503, reason.code, true);
    }
    throw reason;
  }
  const payload = (await response.json().catch(() => null)) as unknown;
  if (!response.ok) {
    const rawDetail = detailFromPayload(payload, response.status);
    const detail =
      rawDetail === "desktop_token_invalid"
        ? "launcher_token_invalid"
        : rawDetail;
    throw new SocialWriteApiError(
      response.status,
      detail,
      response.status === 503 && detail === "sqlite_busy_retry_exhausted",
    );
  }
  if (
    typeof payload !== "object" ||
    payload === null ||
    !("schema_version" in payload) ||
    payload.schema_version !== "owner-manual-social-v1"
  ) {
    throw new SocialWriteApiError(502, "manual_social_schema_mismatch");
  }
  return payload as T;
}

export function getManualSocialFeed(
  worldId: string,
  options: ManualSocialReadOptions = {},
): Promise<ManualSocialFeedRead> {
  return socialWriteRequest<ManualSocialFeedRead>(
    `/api/backend/worlds/${encodeURIComponent(worldId)}/manual-social/feed`,
    { signal: options.signal },
  ).then((result) =>
    assertWorldScopedFeed(
      result,
      worldId,
      null,
      options.ownerWorldCharacterId,
    ),
  );
}

export async function getManualSocialPostThread(
  worldId: string,
  postId: string,
  options: ManualSocialReadOptions = {},
): Promise<ManualSocialFeedRead> {
  const result = await socialWriteRequest<ManualSocialFeedRead>(
    `/api/backend/worlds/${encodeURIComponent(worldId)}/manual-social/posts/${encodeURIComponent(postId)}`,
    { signal: options.signal },
  );
  return assertWorldScopedFeed(
    result,
    worldId,
    postId,
    options.ownerWorldCharacterId,
  );
}

function assertWorldScopedFeed(
  result: ManualSocialFeedRead,
  worldId: string,
  rootPostId: string | null,
  ownerWorldCharacterId?: string,
): ManualSocialFeedRead {
  if (
    !Array.isArray(result.items) ||
    result.items.some(
      (item) =>
        !Number.isInteger(item.reply_count) ||
        item.reply_count < 0 ||
        !Number.isInteger(item.like_count) ||
        item.like_count < 0,
    )
  ) {
    throw new SocialWriteApiError(502, "manual_social_count_schema_mismatch");
  }
  const worldScopeMismatch =
    result.world_id !== worldId ||
    result.items.some((item) => item.world_id !== worldId) ||
    (ownerWorldCharacterId !== undefined &&
      result.owner_world_character_id !== ownerWorldCharacterId);
  const uniqueItemIds = new Set(result.items.map((item) => item.id));
  const threadScopeMismatch =
    rootPostId !== null &&
    (result.items.length === 0 ||
      result.items[0]?.id !== rootPostId ||
      result.items[0]?.reply_to_post_id !== null ||
      uniqueItemIds.size !== result.items.length ||
      result.items
        .slice(1)
        .some((item) => item.reply_to_post_id !== rootPostId));

  if (worldScopeMismatch || threadScopeMismatch) {
    throw new SocialWriteApiError(
      502,
      rootPostId === null
        ? "manual_social_feed_scope_mismatch"
        : "manual_social_thread_scope_mismatch",
    );
  }
  return result;
}

export function createOwnerManualPost(
  worldId: string,
  data: { title: string; body: string },
  idempotencyKey: string,
  ownerWorldCharacterId: string,
): Promise<ManualSocialWriteRead> {
  return socialWriteRequest<ManualSocialWriteRead>(
    `/api/backend/worlds/${encodeURIComponent(worldId)}/manual-social/posts`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify(data),
    },
  ).then((result) =>
    assertOwnerManualWrite(result, {
      operation: "post",
      ownerWorldCharacterId,
      replyToPostId: null,
      worldId,
    }),
  );
}

export function createOwnerManualReply(
  worldId: string,
  postId: string,
  body: string,
  idempotencyKey: string,
  ownerWorldCharacterId: string,
): Promise<ManualSocialWriteRead> {
  return socialWriteRequest<ManualSocialWriteRead>(
    `/api/backend/worlds/${encodeURIComponent(worldId)}/manual-social/posts/${encodeURIComponent(postId)}/replies`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify({ body }),
    },
  ).then((result) =>
    assertOwnerManualWrite(result, {
      operation: "reply",
      ownerWorldCharacterId,
      replyToPostId: postId,
      worldId,
    }),
  );
}

function assertOwnerManualWrite(
  result: ManualSocialWriteRead,
  expected: {
    operation: "post" | "reply";
    ownerWorldCharacterId: string;
    replyToPostId: string | null;
    worldId: string;
  },
): ManualSocialWriteRead {
  const mismatch =
    result.operation !== expected.operation ||
    result.post.world_id !== expected.worldId ||
    result.post.author_world_character_id !== expected.ownerWorldCharacterId ||
    result.post.reply_to_post_id !== expected.replyToPostId ||
    result.delivery.provider_call_count !== 0 ||
    result.delivery.public_reaction_required !== false;
  if (mismatch) {
    throw new SocialWriteApiError(502, "manual_social_write_scope_mismatch");
  }
  return result;
}
