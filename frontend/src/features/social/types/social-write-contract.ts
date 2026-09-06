export type SocialOwnerActor = {
  world_character_id: string;
  world_id: string;
  profile: {
    avatar_url: string;
    display_name: string;
  };
};

export type ManualSocialPostRead = {
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
  can_owner_reply: boolean;
  reply_count: number;
  like_count: number;
  author_profile_capability: "available" | "unavailable";
};

export type ManualSocialWritePostRead = Omit<
  ManualSocialPostRead,
  "reply_count" | "like_count"
>;

export type ManualSocialFeedRead = {
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
