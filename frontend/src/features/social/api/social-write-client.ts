import { RuntimeFetchError, runtimeFetch } from "@/lib/runtime/runtime-config";

import type { ManualSocialFeedRead, ManualSocialThreadRead, ManualSocialLikeRead, ManualSocialWriteRead } from "@/features/social/types/social-write-contract";
import { buildReplyTree } from "../utils/reply-tree";

type ManualSocialReadOptions = {
  offset?: number;
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
  schema: string | null = "owner-manual-social-v1",
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
  if (schema && (
    typeof payload !== "object" ||
    payload === null ||
    !("schema_version" in payload) ||
    payload.schema_version !== schema
  )) {
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
): Promise<ManualSocialThreadRead> {
  const result = await socialWriteRequest<ManualSocialThreadRead>(
    `/api/backend/worlds/${encodeURIComponent(worldId)}/manual-social/posts/${encodeURIComponent(postId)}${options.offset === undefined ? "" : `?offset=${options.offset}`}`,
    { signal: options.signal },
    "owner-manual-social-thread-v2",
  );
  return assertWorldScopedThread(result, worldId, postId, options.ownerWorldCharacterId);
}

export function assertWorldScopedThread(result: ManualSocialThreadRead, worldId: string, postId: string, ownerId?: string): ManualSocialThreadRead {
  const all = [result.selected_post, ...(Array.isArray(result.replies) ? result.replies : [])];
  const refs = Array.isArray(result.parent_references) ? result.parent_references : [];
  if (result.schema_version !== "owner-manual-social-thread-v2" || result.world_id !== worldId || !result.owner_world_character_id ||
      (ownerId !== undefined && result.owner_world_character_id !== ownerId) || result.selected_post?.id !== postId ||
      typeof result.root_post_id !== "string" || !result.root_post_id || !Array.isArray(result.replies) || !Array.isArray(result.parent_references) ||
      new Set(all.map(p => p?.id)).size !== all.length || !Number.isInteger(result.page_offset) || result.page_offset < 0 ||
      (result.next_offset !== null && (!Number.isInteger(result.next_offset) || result.next_offset <= result.page_offset)) ||
      all.some(p => !p || p.world_id !== worldId || p.thread_root_post_id !== result.root_post_id || !Number.isInteger(p.reply_count) || p.reply_count < 0 || !Number.isInteger(p.like_count) || p.like_count < 0 || !p.author_world_character_id) ||
      refs.some(r => !r.post_id || !["available","unavailable"].includes(r.state)) ||
      (result.selected_post.reply_to_post_id === null ? result.parent !== null || result.root_post_id !== postId : result.parent?.post_id !== result.selected_post.reply_to_post_id) ||
      result.replies.some(p => !p.reply_to_post_id || !refs.some(r => r.post_id === p.reply_to_post_id)) ||
      all.some(p => p.reply_to_post_id === p.id)) {
    throw new SocialWriteApiError(502,"manual_social_thread_scope_mismatch",true);
  }
  try { buildReplyTree([result.selected_post, ...result.replies], result.root_post_id); }
  catch { throw new SocialWriteApiError(502,"manual_social_thread_scope_mismatch",true); }
  return result;
}

export async function setOwnerManualLike(worldId: string, postId: string, ownerId: string, liked: boolean): Promise<ManualSocialLikeRead> {
  const result = await socialWriteRequest<ManualSocialLikeRead>(`/api/backend/worlds/${encodeURIComponent(worldId)}/manual-social/posts/${encodeURIComponent(postId)}/like`, { method: liked ? "PUT" : "DELETE" }, null);
  if (result.world_id !== worldId || result.post_id !== postId || result.owner_world_character_id !== ownerId ||
      !["liked","not_liked"].includes(result.viewer_like_state) || !Number.isInteger(result.like_count) || result.like_count < 0 || result.can_owner_like !== true) {
    throw new SocialWriteApiError(502,"manual_social_like_scope_mismatch",true);
  }
  return result;
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
        item.like_count < 0 ||
        typeof item.author_world_character_id !== "string" ||
        !["available", "unavailable"].includes(item.author_profile_capability),
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
      result.items[0]?.id !== (result.root_post_id ?? rootPostId)
      || (result.target_post_id !== undefined && result.target_post_id !== rootPostId) ||
      result.items[0]?.reply_to_post_id !== null ||
      uniqueItemIds.size !== result.items.length ||
      result.items
        .slice(1)
        .some((item) => item.reply_to_post_id === null || (
          item.thread_root_post_id != null
            ? item.thread_root_post_id !== (result.root_post_id ?? rootPostId)
            : item.reply_to_post_id !== (result.root_post_id ?? rootPostId)
        )));

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
  data: { title: string; body: string; attachment_asset_id?: string },
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
