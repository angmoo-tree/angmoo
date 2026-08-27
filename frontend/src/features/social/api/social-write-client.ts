import {
  RuntimeFetchError,
  runtimeFetch,
} from "@/shared/runtime/public";

import type {
  ManualSocialFeedRead,
  ManualSocialWriteRead,
} from "../model/social-write-contract";

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
  options: { signal?: AbortSignal } = {},
): Promise<ManualSocialFeedRead> {
  return socialWriteRequest<ManualSocialFeedRead>(
    `/api/backend/worlds/${encodeURIComponent(worldId)}/manual-social/feed`,
    { signal: options.signal },
  );
}

export async function getManualSocialPostThread(
  worldId: string,
  postId: string,
  options: { signal?: AbortSignal } = {},
): Promise<ManualSocialFeedRead> {
  const result = await socialWriteRequest<ManualSocialFeedRead>(
    `/api/backend/worlds/${encodeURIComponent(worldId)}/manual-social/posts/${encodeURIComponent(postId)}`,
    { signal: options.signal },
  );
  if (
    result.world_id !== worldId ||
    result.items.length === 0 ||
    result.items[0]?.id !== postId ||
    result.items[0]?.reply_to_post_id !== null ||
    result.items.some((item) => item.world_id !== worldId)
  ) {
    throw new SocialWriteApiError(502, "manual_social_thread_scope_mismatch");
  }
  return result;
}

export function createOwnerManualPost(
  worldId: string,
  data: { title: string; body: string },
  idempotencyKey: string,
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
  );
}

export function createOwnerManualReply(
  worldId: string,
  postId: string,
  body: string,
  idempotencyKey: string,
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
  );
}
