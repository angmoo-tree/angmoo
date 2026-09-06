export type WorldAppWorldRead = {
  world_id: string;
  name: string;
  tagline: string;
  banner_media_id: string | null;
  banner_alt_text: string;
  status: "draft" | "published" | "archived";
  visibility: "private" | "unlisted" | "public";
  readiness_status: "not_ready" | "publish_ready" | "stale";
  membership_role: "owner" | "editor" | "member";
  updated_at: string;
  launchable: boolean;
  launch_block_reason:
    | "world_archived"
    | "world_not_published"
    | "world_not_ready"
    | "world_private"
    | null;
};

export type LocalWorldAppRead = {
  schema_version: "local-world-app-v1";
  surface: "world_app";
  world: WorldAppWorldRead;
};

export type OwnerControlledActorRead = {
  schema_version: "owner-controlled-world-character-v1";
  world_character_id: string;
  world_id: string;
  character_id: string;
  control_mode: "owner_controlled";
  status: string;
  autonomous_enabled: false;
  version: number;
  profile: {
    display_name: string;
    avatar_url: string;
    intro: string;
    role_key: string | null;
    preferred_address: string;
    interests: string[];
    background: string;
  };
};

