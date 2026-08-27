export type FeedContentFilter = "all" | "posts" | "reposts";

export type PostInfoKind =
  | "weather"
  | "news"
  | "calendar"
  | "market"
  | "knowledge"
  | "other";

export type MentionedCharacterRef = {
  handle: string;
  character_id: string;
  name: string;
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

export type FeedPage = {
  items: PostSummary[];
  next_cursor: string | null;
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
