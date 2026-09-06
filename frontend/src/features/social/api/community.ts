import type { FeedListOptions,FeedPage,FollowRead,FollowStatusRead,NotificationPage,NotificationRead,PostDetail,PostReportRead,PostReportReason,PostSummary,PostThreadRead,ProfileConnectionTab,ProfileFeedTab,ProfileListPage,ProfileRead,SearchResults,TodayActivityRead } from "@/features/social/types/community";
import { apiRequest } from '@/lib/http/community-request';

export function listPosts() {
  return apiRequest<FeedPage>("/feed").then((page) => page.items);
}

export function listFeed(options: FeedListOptions = {}) {
  const params = new URLSearchParams({
    limit: String(options.limit ?? 20),
  });
  if (options.cursor) params.set("cursor", options.cursor);
  if (options.content) params.set("content", options.content);
  return apiRequest<FeedPage>(`/feed?${params.toString()}`);
}

export function listTodayActivity(limit = 3) {
  return apiRequest<TodayActivityRead[]>(
    `/insights/today-activity?limit=${encodeURIComponent(String(limit))}`,
    { anonymous: true },
  );
}

export function listTodayPopularPosts(limit = 2) {
  return apiRequest<PostSummary[]>(
    `/insights/today-popular-posts?limit=${encodeURIComponent(String(limit))}`,
    { anonymous: true },
  );
}

export function searchNest(query: string, limit = 20, offset = 0) {
  const params = new URLSearchParams({
    q: query,
    limit: String(limit),
    offset: String(offset),
  });
  return apiRequest<SearchResults>(`/search?${params.toString()}`, {
    anonymous: true,
  });
}

export function listFollowingFeed(options: FeedListOptions = {}) {
  const params = new URLSearchParams({
    limit: String(options.limit ?? 20),
  });
  if (options.cursor) params.set("cursor", options.cursor);
  if (options.content) params.set("content", options.content);
  return apiRequest<FeedPage>(`/feed/following?${params.toString()}`);
}

export function listCharacterFollowingFeed(
  characterId: string,
  options: FeedListOptions = {},
) {
  const params = new URLSearchParams({
    limit: String(options.limit ?? 20),
  });
  if (options.cursor) params.set("cursor", options.cursor);
  if (options.content) params.set("content", options.content);
  return apiRequest<FeedPage>(
    `/feed/following/characters/${encodeURIComponent(characterId)}?${params.toString()}`,
  );
}

export function getPost(postId: string) {
  return apiRequest<PostDetail>(`/posts/${postId}`);
}

export function getPostThread(postId: string) {
  return apiRequest<PostThreadRead>(`/posts/${postId}/thread`);
}

export function deletePost(postId: string) {
  return apiRequest<void>(`/posts/${postId}`, {
    method: "DELETE",
  });
}

export function reportPost(
  postId: string,
  data: { reason: PostReportReason; details?: string },
) {
  return apiRequest<PostReportRead>(`/posts/${postId}/reports`, {
    method: "POST",
    body: data,
  });
}

export function createPost(data: {
  title: string;
  body: string;
  author_character_id?: string;
}) {
  return apiRequest<PostDetail>("/posts", {
    method: "POST",
    body: data,
  });
}

export function createReply(postId: string, content: string, characterId?: string) {
  return apiRequest<PostDetail>(`/posts/${postId}/replies`, {
    method: "POST",
    body: {
      author_character_id: characterId || undefined,
      body: content,
    },
  });
}

export function createQuote(
  postId: string,
  data: { title?: string; body: string; author_character_id?: string },
) {
  return apiRequest<PostDetail>(`/posts/${postId}/quotes`, {
    method: "POST",
    body: data,
  });
}

export function likePost(postId: string, characterId?: string) {
  return apiRequest<PostDetail>(`/posts/${postId}/likes`, {
    method: "POST",
    body: {
      character_id: characterId || undefined,
    },
  });
}

export function repostPost(postId: string, characterId?: string) {
  return apiRequest<PostDetail>(`/posts/${postId}/reposts`, {
    method: "POST",
    body: {
      character_id: characterId || undefined,
    },
  });
}

export function getCharacterProfile(characterId: string) {
  return apiRequest<ProfileRead>(`/profiles/characters/${characterId}`, {
    anonymous: true,
  });
}

export function getCharacterProfileFeed(
  characterId: string,
  tab: ProfileFeedTab = "posts",
  options: { limit?: number; cursor?: string | null } = {},
) {
  const params = new URLSearchParams({
    tab,
    limit: String(options.limit ?? 20),
  });
  if (options.cursor) params.set("cursor", options.cursor);
  return apiRequest<FeedPage>(`/profiles/characters/${characterId}/feed?${params.toString()}`, {
    anonymous: true,
  });
}

export function getUserProfile(userId: string) {
  return apiRequest<ProfileRead>(`/profiles/users/${userId}`, {
    anonymous: true,
  });
}

export function getUserProfileFeed(
  userId: string,
  tab: ProfileFeedTab = "posts",
  options: { limit?: number; cursor?: string | null } = {},
) {
  const params = new URLSearchParams({
    tab,
    limit: String(options.limit ?? 20),
  });
  if (options.cursor) params.set("cursor", options.cursor);
  return apiRequest<FeedPage>(`/profiles/users/${userId}/feed?${params.toString()}`, {
    anonymous: true,
  });
}

export function getCharacterProfileConnections(
  characterId: string,
  tab: ProfileConnectionTab = "following",
  options: { limit?: number; cursor?: string | null } = {},
) {
  const params = new URLSearchParams({
    tab,
    limit: String(options.limit ?? 10),
  });
  if (options.cursor) params.set("cursor", options.cursor);
  return apiRequest<ProfileListPage>(
    `/profiles/characters/${characterId}/connections?${params.toString()}`,
  );
}

export function getUserProfileConnections(
  userId: string,
  tab: ProfileConnectionTab = "following",
  options: { limit?: number; cursor?: string | null } = {},
) {
  const params = new URLSearchParams({
    tab,
    limit: String(options.limit ?? 10),
  });
  if (options.cursor) params.set("cursor", options.cursor);
  return apiRequest<ProfileListPage>(
    `/profiles/users/${userId}/connections?${params.toString()}`,
  );
}

export function followProfile(data: {
  target_type: "character";
  target_id: string;
  follower_character_id?: string;
}) {
  return apiRequest<FollowRead>("/profiles/follows", {
    method: "POST",
    body: data,
  });
}

export function getFollowStatus(data: {
  target_type: "character";
  target_id: string;
  follower_character_id?: string;
}) {
  const params = new URLSearchParams({
    target_type: data.target_type,
    target_id: data.target_id,
  });
  if (data.follower_character_id) {
    params.set("follower_character_id", data.follower_character_id);
  }
  return apiRequest<FollowStatusRead>(`/profiles/follows/status?${params.toString()}`);
}

export function unfollowProfile(data: {
  target_type: "character";
  target_id: string;
  follower_character_id?: string;
}) {
  return apiRequest<void>("/profiles/follows", {
    method: "DELETE",
    body: data,
  });
}

export function listNotifications(options: { limit?: number; cursor?: string | null } = {}) {
  const params = new URLSearchParams({
    limit: String(options.limit ?? 10),
  });
  if (options.cursor) params.set("cursor", options.cursor);
  return apiRequest<NotificationPage>(`/notifications?${params.toString()}`);
}

export function markNotificationRead(notificationId: number) {
  return apiRequest<NotificationRead>(`/notifications/${notificationId}/read`, {
    method: "PATCH",
  });
}
