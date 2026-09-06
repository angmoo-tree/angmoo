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
  recent_comments: { id: number; post_id: string; author_character_id: string; content: string; created_at: string }[];
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
