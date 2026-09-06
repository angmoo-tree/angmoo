export type WorldCharacterProfileCapability = "available";

export type WorldCharacterPublicProfile = {
  schema_version: "world-character-profile-v1";
  world_id: string;
  world_character_id: string;
  character_id: string;
  display_name: string;
  handle: string | null;
  avatar_url: string | null;
  banner_url: string | null;
  intro: string;
  role_key: string | null;
  control_mode: "autonomous" | "owner_controlled";
  status: "active";
  profile_capability: WorldCharacterProfileCapability;
};

export type WorldCharacterProfileListRead = {
  schema_version: "world-character-profile-list-v1";
  world_id: string;
  items: WorldCharacterPublicProfile[];
};
