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

export type FeedListOptions = {
  limit?: number;
  cursor?: string | null;
  content?: FeedContentFilter;
};
