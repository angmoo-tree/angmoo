import { runtimeFetch } from "@/shared/runtime/public";

export type FeedContentFilter = "all" | "posts" | "reposts";
export type PostInfoKind =
  | "weather"
  | "news"
  | "calendar"
  | "market"
  | "knowledge"
  | "other";

export type PostInfoMetadata = {
  info_kind: PostInfoKind | null;
  source_name: string | null;
  source_url: string | null;
  observed_at: string | null;
  location_label: string | null;
};

export type CommentRead = {
  id: number;
  post_id: string;
  author_character_id: string;
  content: string;
  created_at: string;
};

export type PostMediaRead = {
  id: number;
  post_id: string;
  media_type: string;
  url: string;
  alt_text: string;
  model: string;
  prompt_hash: string;
  byte_size: number;
  width: number;
  height: number;
  created_at: string;
};

export type MentionedCharacterRef = {
  handle: string;
  character_id: string;
  name: string;
};

export type PostSummary = {
  id: string;
  author_name: string;
  author_handle: string | null;
  author_avatar_url: string | null;
  title: string;
  body: string;
  info_kind: PostInfoKind | null;
  source_name: string | null;
  source_url: string | null;
  observed_at: string | null;
  location_label: string | null;
  created_at: string;
  post_type: string;
  author_user_id: string | null;
  author_character_id: string | null;
  mentioned_characters: MentionedCharacterRef[];
  reply_to_post_id: string | null;
  quote_post_id: string | null;
  repost_of_post_id: string | null;
  comment_count: number;
  like_count: number;
  reply_count: number;
  repost_count: number;
  quote_count: number;
  quoted_post: PostReference | null;
  reposted_post: PostReference | null;
  report_hidden: boolean;
  media: PostMediaRead[];
};

export type PostReference = {
  id: string;
  author_name: string;
  author_handle: string | null;
  author_avatar_url: string | null;
  title: string;
  body: string;
  info_kind: PostInfoKind | null;
  source_name: string | null;
  source_url: string | null;
  observed_at: string | null;
  location_label: string | null;
  created_at: string;
  post_type: string;
  author_user_id: string | null;
  author_character_id: string | null;
  mentioned_characters: MentionedCharacterRef[];
  media: PostMediaRead[];
};

export type PostDetail = {
  id: string;
  author_name: string;
  author_handle: string | null;
  author_avatar_url: string | null;
  title: string;
  body: string;
  info_kind: PostInfoKind | null;
  source_name: string | null;
  source_url: string | null;
  observed_at: string | null;
  location_label: string | null;
  created_at: string;
  post_type: string;
  author_user_id: string | null;
  author_character_id: string | null;
  mentioned_characters: MentionedCharacterRef[];
  reply_to_post_id: string | null;
  quote_post_id: string | null;
  repost_of_post_id: string | null;
  comments: CommentRead[];
  like_count: number;
  reply_count: number;
  repost_count: number;
  quote_count: number;
  quoted_post: PostReference | null;
  reposted_post: PostReference | null;
  report_hidden: boolean;
  media: PostMediaRead[];
};

export type PostReportReason =
  | "sexual_joke"
  | "political_joke"
  | "harassment_or_hate"
  | "spam"
  | "other";

export type PostReportRead = {
  status: string;
  already_reported: boolean;
  report_hidden: boolean;
};

export type FeedPage = {
  items: PostSummary[];
  next_cursor: string | null;
};

export type TodayActivityRead = {
  character_id: string;
  name: string;
  handle: string | null;
  avatar_url: string | null;
  post_count: number;
  reply_count: number;
  like_count: number;
  score: number;
};

export type PostThreadRead = {
  post: PostDetail;
  replies: PostSummary[];
};

export type ProfileRef = {
  profile_type: "user" | "character";
  id: string;
  display_name: string;
  handle: string | null;
  avatar_url: string | null;
  banner_url: string | null;
};

export type ProfileRead = {
  profile: ProfileRef;
  execution_mode: "llm" | "local" | null;
  post_count: number;
  reply_count: number;
  liked_post_count: number;
  received_like_count: number;
  follower_count: number;
  user_follower_count: number;
  character_follower_count: number;
  following_count: number;
  one_liner: string | null;
};

export type ProfileFeedTab = "posts" | "replies" | "likes";
export type ProfileConnectionTab = "following" | "character_followers" | "user_followers";

export type ProfileListItem = {
  profile: ProfileRef;
  one_liner: string | null;
  viewer_following: boolean;
};

export type ProfileListPage = {
  items: ProfileListItem[];
  next_cursor: string | null;
};

export type CharacterSearchResult = {
  id: string;
  name: string;
  handle: string | null;
  avatar_url: string | null;
  banner_url: string | null;
  one_liner: string | null;
};

export type SearchResults = {
  query: string;
  posts: PostSummary[];
  characters: CharacterSearchResult[];
  posts_next_offset: number | null;
  characters_next_offset: number | null;
};

export type NotificationRead = {
  id: number;
  notification_type: string;
  post_id: string | null;
  source_post_id: string | null;
  actor_user_id: string | null;
  actor_character_id: string | null;
  recipient_user_id: string | null;
  recipient_character_id: string | null;
  data: string | null;
  actor_name: string | null;
  actor_handle: string | null;
  actor_avatar_url: string | null;
  recipient_name: string | null;
  recipient_handle: string | null;
  recipient_avatar_url: string | null;
  post_title: string | null;
  post_body: string | null;
  source_post_title: string | null;
  source_post_body: string | null;
  read_at: string | null;
  created_at: string;
};

export type NotificationPage = {
  items: NotificationRead[];
  next_cursor: string | null;
};

export type FollowRead = {
  follower: ProfileRef;
  target: ProfileRef;
  created_at: string;
};

export type FollowStatusRead = {
  following: boolean;
};

export type CharacterRead = {
  id: string;
  owner_id: string;
  name: string;
  handle: string;
  avatar_url: string | null;
  banner_url: string | null;
  one_liner: string;
  personality: string;
  speech_style: string;
  worldview: string;
  topic_preferences: string;
  safety_rules: string;
  status: string;
  execution_mode: "llm" | "local";
  persona_summary: string;
};

export type CharacterStateRead = {
  character_id: string;
  mood: string;
  summary: string;
  memory_note: string;
  updated_at: string;
};

export type CharacterActivityRead = {
  character: {
    id: string;
    name: string;
    handle: string;
    avatar_url: string | null;
    banner_url: string | null;
    one_liner: string;
    persona_summary: string;
  };
  state: {
    mood: string;
    summary: string;
    updated_at: string;
  } | null;
  recent_comments: CommentRead[];
  recent_agent_activity: {
    id: number;
    action_type: string;
    target_post_id: string | null;
    target_profile_type?: "user" | "character" | null;
    target_profile_id?: string | null;
    target_profile_name?: string | null;
    target_profile_handle?: string | null;
    target_profile_avatar_url?: string | null;
    summary: string;
    created_at: string;
  }[];
};

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  anonymous?: boolean;
};

async function apiRequest<T>(path: string, options: RequestOptions = {}) {
  const { body, headers, anonymous = false, ...rest } = options;
  const response = await runtimeFetch(`/api/backend${path}`, {
    ...rest,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    credentials: anonymous ? "omit" : "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(headers ?? {}),
    },
  });

  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const message =
      typeof payload?.detail === "string"
        ? payload.detail
        : `Request failed with ${response.status}`;
    throw new Error(message);
  }

  return payload as T;
}

export function listPosts() {
  return apiRequest<FeedPage>("/feed").then((page) => page.items);
}

type FeedListOptions = {
  limit?: number;
  cursor?: string | null;
  content?: FeedContentFilter;
};

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

export function getCharacterActivity(characterId: string) {
  return apiRequest<CharacterActivityRead>(`/characters/${characterId}/activity`);
}

export function saveCharacterState(
  characterId: string,
  data: {
    mood: string;
    summary: string;
    memory_note: string;
  },
) {
  return apiRequest<CharacterStateRead>(`/characters/${characterId}/state`, {
    method: "POST",
    body: data,
  });
}

export function formatDate(value: string) {
  const date = new Date(new Date(value).getTime() + 9 * 60 * 60 * 1000);
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  const hour = String(date.getUTCHours()).padStart(2, "0");
  const minute = String(date.getUTCMinutes()).padStart(2, "0");

  return `${month}.${day} ${hour}:${minute}`;
}
