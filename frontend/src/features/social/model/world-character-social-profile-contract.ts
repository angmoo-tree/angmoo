import type {
  MentionedCharacterRef,
  PostMediaRead,
} from "./social-feed-contract";

export type WorldCharacterSocialProfileTab = "posts" | "replies" | "likes";

export type WorldCharacterSocialProfileCounts = {
  post_count: number;
  reply_count: number;
  liked_post_count: number;
  received_like_count: number;
};

export type WorldCharacterSocialProfilePost = {
  id: string;
  world_id: string;
  author_world_character_id: string;
  author_name: string;
  author_handle: string | null;
  author_avatar_url: string | null;
  title: string;
  body: string;
  post_type: string;
  reply_to_post_id: string | null;
  created_at: string;
  reply_count: number;
  like_count: number;
  author_profile_capability: "available" | "unavailable";
  mentioned_characters: MentionedCharacterRef[];
  media: PostMediaRead[];
};

export type WorldCharacterSocialProfileRead = {
  schema_version: "world-character-social-profile-v1";
  world_id: string;
  world_character_id: string;
  character_id: string;
  counts: WorldCharacterSocialProfileCounts;
  tab: WorldCharacterSocialProfileTab;
  items: WorldCharacterSocialProfilePost[];
  next_cursor: string | null;
};

export function parseWorldCharacterSocialProfileTab(
  value: string | null | undefined,
): WorldCharacterSocialProfileTab {
  return value === "replies" || value === "likes" ? value : "posts";
}
