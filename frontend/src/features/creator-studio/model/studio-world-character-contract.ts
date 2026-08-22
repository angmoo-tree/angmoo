export type StudioWorldCharacterRead = {
  world_character_id: string;
  character_id: string;
  display_name: string;
  avatar_url: string | null;
  intro: string;
  role_key: string | null;
  control_mode: "autonomous" | "owner_controlled";
  status: string;
  autonomous_enabled: boolean;
  version: number;
  activity_setup_state:
    | "not_started"
    | "generated"
    | "approved"
    | "unavailable_for_owner_controlled";
};

export type StudioWorldCharacterListRead = {
  schema_version: "studio-world-character-list-v1";
  world_id: string;
  items: StudioWorldCharacterRead[];
};
