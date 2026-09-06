export type StudioWorldCharacterRead = {
  world_character_id: string;
  character_id: string;
  display_name: string;
  confirmation_name: string;
  avatar_url: string | null;
  intro: string;
  role_key: string | null;
  control_mode: "autonomous" | "owner_controlled";
  status: string;
  autonomous_enabled: boolean;
  selected_active_world: boolean;
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

export type StudioCharacterCandidateRead = {
  character_id: string;
  display_name: string;
  handle: string | null;
  avatar_url: string | null;
  current_world_status: string | null;
  eligible: boolean;
  reason_code:
    | "already_linked"
    | "character_moderation_inactive"
    | "local_execution_mode_unsupported"
    | "world_character_ineligible"
    | "world_character_left_restore_unsupported"
    | null;
};

export type StudioCharacterCandidateListRead = {
  schema_version: "studio-character-candidates-v1";
  world_id: string;
  items: StudioCharacterCandidateRead[];
};

export type StudioWorldRole = {
  key: string;
  name: string;
  autonomous_allowed: boolean;
};

export type WorldCharacterEntryRead = {
  id: string;
  world_id: string;
  character_id: string;
  membership_id: string;
  role_key: string | null;
  status: string;
  autonomous_enabled: boolean;
  version: number;
  reused: boolean;
};

export type WorldCharacterLeaveRead = {
  world_character_id: string;
  world_id: string;
  character_id: string;
  status: "left";
  autonomous_enabled: false;
  version: number;
  scheduler_assignment_released: boolean;
  history_preserved: true;
  replayed: boolean;
};
