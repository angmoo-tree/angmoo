import { fetchBackendJson } from "@/lib/backend";
import { runtimeFetch } from "@/shared/runtime/public";

import type {
  FeedContentFilter,
  FeedPage,
  PostReportRead,
  PostReportReason,
} from "../model/social-feed-contract";

type FeedListOptions = {
  limit?: number;
  cursor?: string | null;
  content?: FeedContentFilter;
};

type RequestOptions = Omit<RequestInit, "body"> & { body?: unknown };

async function socialRequest<T>(path: string, options: RequestOptions = {}) {
  const { body, headers, ...rest } = options;
  const response = await runtimeFetch(`/api/backend${path}`, {
    ...rest,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(headers ?? {}) },
  });
  const payload = (await response.json().catch(() => null)) as unknown;
  if (!response.ok) {
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
  return socialRequest<FeedPage>(feedPath("/feed", options));
}

export function listFollowingSocialFeed(options: FeedListOptions = {}) {
  return socialRequest<FeedPage>(feedPath("/feed/following", options));
}

export function listCharacterFollowingSocialFeed(
  characterId: string,
  options: FeedListOptions = {},
) {
  return socialRequest<FeedPage>(
    feedPath(
      `/feed/following/characters/${encodeURIComponent(characterId)}`,
      options,
    ),
  );
}

export function deleteSocialPost(postId: string) {
  return socialRequest<void>(`/posts/${encodeURIComponent(postId)}`, {
    method: "DELETE",
  });
}

export function reportSocialPost(
  postId: string,
  data: { reason: PostReportReason; details?: string },
) {
  return socialRequest<PostReportRead>(
    `/posts/${encodeURIComponent(postId)}/reports`,
    { method: "POST", body: data },
  );
}

export function formatSocialDate(value: string) {
  const date = new Date(new Date(value).getTime() + 9 * 60 * 60 * 1000);
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  const hour = String(date.getUTCHours()).padStart(2, "0");
  const minute = String(date.getUTCMinutes()).padStart(2, "0");
  return `${month}.${day} ${hour}:${minute}`;
}
