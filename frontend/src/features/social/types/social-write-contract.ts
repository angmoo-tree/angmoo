import type { PostMediaRead } from "./social-feed-contract";
export type SocialOwnerActor = {
  world_character_id: string;
  world_id: string;
  profile: {
    avatar_url: string | null;
    display_name: string;
    handle?: string | null;
    deleted?: boolean;
  };
};

export type ManualSocialPostRead = {
  media?: PostMediaRead[];
  thread_root_post_id?: string | null;
  id: string;
  world_id: string;
  author_world_character_id: string;
  author_name: string;
  author_deleted?: boolean;
  author_handle: string | null;
  author_avatar_url: string | null;
  title: string;
  body: string;
  post_type: string;
  reply_to_post_id: string | null;
  created_at: string;
  can_owner_reply: boolean;
  reply_count: number;
  like_count: number;
  author_profile_capability: "available" | "unavailable";
  viewer_like_state?: "liked" | "not_liked" | "unavailable";
  can_owner_like?: boolean;
  reaction_world_id?: string | null;
  reaction_owner_world_character_id?: string | null;
};

export type ManualSocialParentRead = { post_id: string; state: "available" | "unavailable" };
export type ManualSocialThreadRead = {
  schema_version: "owner-manual-social-thread-v2";
  world_id: string;
  owner_world_character_id: string;
  selected_post: ManualSocialPostRead;
  root_post_id: string;
  parent: ManualSocialParentRead | null;
  parent_references: ManualSocialParentRead[];
  replies: ManualSocialPostRead[];
  page_offset: number;
  next_offset: number | null;
};

export type ManualSocialLikeRead = {
  world_id: string; post_id: string; owner_world_character_id: string;
  viewer_like_state: "liked" | "not_liked"; like_count: number; can_owner_like: true;
};

export type ManualSocialWritePostRead = Omit<
  ManualSocialPostRead,
  "reply_count" | "like_count"
>;

export type ManualSocialFeedRead = {
  root_post_id?: string | null;
  target_post_id?: string | null;
  page_offset?: number;
  next_offset?: number | null;
  schema_version: "owner-manual-social-v1";
  world_id: string;
  owner_world_character_id: string;
  items: ManualSocialPostRead[];
};

export type ManualSocialWriteRead = {
  schema_version: "owner-manual-social-v1";
  operation: "post" | "reply";
  replayed: boolean;
  post: ManualSocialWritePostRead;
  delivery: {
    provider_call_count: 0;
    inbox_candidate_id: string | null;
    inbox_status: "not_applicable" | "pending";
    public_reaction_required: false;
  };
};
