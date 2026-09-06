import {requestSocialApi} from '@/lib/http/social-request';
export {requestSocialApi} from '@/lib/http/social-request';
import { formatDate } from "@/utils/profile-presentation";

import type { FeedContentFilter, FeedPage, PostThreadRead, PostReportRead, PostReportReason } from "@/features/social/types/social-feed-contract";

type FeedListOptions = {
  limit?: number;
  cursor?: string | null;
  content?: FeedContentFilter;
};

function feedPath(path: string, options: FeedListOptions): string {
  const params = new URLSearchParams({ limit: String(options.limit ?? 20) });
  if (options.cursor) params.set("cursor", options.cursor);
  if (options.content) params.set("content", options.content);
  return `${path}?${params.toString()}`;
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
