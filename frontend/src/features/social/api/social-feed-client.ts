import { fetchBackendJson } from "@/shared/api/public";
import { clearStoredUser, notifyAuthChanged } from "@/shared/auth/public";
import { runtimeFetch } from "@/shared/runtime/public";
import { formatDate } from "@/shared/ui/public";

import type {
  FeedContentFilter,
  FeedPage,
  PostThreadRead,
  PostReportRead,
  PostReportReason,
} from "../model/social-feed-contract";

type FeedListOptions = {
  limit?: number;
  cursor?: string | null;
  content?: FeedContentFilter;
};

type RequestOptions = Omit<RequestInit, "body" | "credentials"> & {
  body?: unknown;
  anonymous?: boolean;
  clearAuthOnUnauthorized?: boolean;
};

export async function requestSocialApi<T>(
  path: string,
  options: RequestOptions = {},
) {
  const {
    anonymous = false,
    body,
    clearAuthOnUnauthorized = false,
    headers,
    ...rest
  } = options;
  const response = await runtimeFetch(`/api/backend${path}`, {
    ...rest,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    credentials: anonymous ? "omit" : "same-origin",
    headers: { "Content-Type": "application/json", ...(headers ?? {}) },
  });
  const text = await response.text();
  let payload: unknown = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch (error) {
    // A successful endpoint must not silently turn a malformed response into a
    // typed null. Error responses still fall through to the stable HTTP reason.
    if (response.ok) throw error;
  }
  if (!response.ok) {
    if (response.status === 401 && !anonymous && clearAuthOnUnauthorized) {
      clearStoredUser();
      notifyAuthChanged();
    }
    const detail =
      typeof payload === "object" &&
      payload !== null &&
      "detail" in payload &&
      typeof payload.detail === "string"
        ? payload.detail
        : `http_${response.status}`;
    throw new Error(detail);
  }
  return payload as T;
}

function feedPath(path: string, options: FeedListOptions): string {
  const params = new URLSearchParams({ limit: String(options.limit ?? 20) });
  if (options.cursor) params.set("cursor", options.cursor);
  if (options.content) params.set("content", options.content);
  return `${path}?${params.toString()}`;
}

export async function getInitialSocialFeed(limit = 10): Promise<FeedPage> {
  return fetchBackendJson<FeedPage>(`/api/v1/feed?limit=${limit}`);
}

export function listSocialFeed(options: FeedListOptions = {}) {
  return requestSocialApi<FeedPage>(feedPath("/feed", options));
}

export function listFollowingSocialFeed(options: FeedListOptions = {}) {
  return requestSocialApi<FeedPage>(feedPath("/feed/following", options));
}

export function listCharacterFollowingSocialFeed(
  characterId: string,
  options: FeedListOptions = {},
) {
  return requestSocialApi<FeedPage>(
    feedPath(
      `/feed/following/characters/${encodeURIComponent(characterId)}`,
      options,
    ),
  );
}

export function getSocialPostThread(postId: string) {
  return requestSocialApi<PostThreadRead>(
    `/posts/${encodeURIComponent(postId)}/thread`,
  );
}

export function deleteSocialPost(postId: string) {
  return requestSocialApi<void>(`/posts/${encodeURIComponent(postId)}`, {
    method: "DELETE",
  });
}

export function reportSocialPost(
  postId: string,
  data: { reason: PostReportReason; details?: string },
) {
  return requestSocialApi<PostReportRead>(
    `/posts/${encodeURIComponent(postId)}/reports`,
    { method: "POST", body: data },
  );
}

export function formatSocialDate(value: string) {
  return formatDate(value);
}
