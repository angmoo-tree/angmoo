export type WorldDaypart = "dawn" | "morning" | "afternoon" | "evening";

export type WorldVisibility = "private" | "unlisted" | "public";

export type WorldJoinPolicy =
  | "open"
  | "approval_required"
  | "invite_only"
  | "private";

export type WorldPlaceInput = {
  key: string;
  name: string;
  description: string;
  available_dayparts: WorldDaypart[];
  access_role_keys: string[];
};

export type WorldRoleInput = {
  key: string;
  name: string;
  description: string;
  responsibilities: string[];
  allowed_activity_scope: string[];
  autonomous_allowed: boolean;
};

export type WorldDaypartProfileInput = {
  daypart: WorldDaypart;
  description: string;
  available_features: string[];
  restricted_features: string[];
};

export type WorldRuleInput = {
  key: string;
  rule_kind: "allow" | "forbid";
  description: string;
};

export type WorldGlossaryTermInput = {
  key: string;
  term: string;
  meaning: string;
};

export type WorldDefinition = {
  name: string;
  tagline: string;
  setting_description: string;
  daily_life_description: string;
  genre_tags: string[];
  tone_tags: string[];
  timezone: string;
  language: string;
  visibility: WorldVisibility;
  join_policy: WorldJoinPolicy;
  additional_generation_guidance: string;
  places: WorldPlaceInput[];
  roles: WorldRoleInput[];
  daypart_profiles: WorldDaypartProfileInput[];
  rules: WorldRuleInput[];
  glossary: WorldGlossaryTermInput[];
};

export type WorldRead = WorldDefinition & {
  id: string;
  slug: string;
  banner_media_id: string | null;
  banner_alt_text: string;
  status: "draft" | "published" | "archived";
  definition_version: number;
  row_version: number;
  contract_version: string;
  contract_hash: string;
  readiness_status: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
};

export type WorldValidationIssue = {
  reason_code: string;
  field: string | null;
  message: string;
};

export type WorldReadiness = {
  world_id: string;
  definition_version: number;
  row_version: number;
  contract_version: string;
  contract_hash: string;
  required_fields: Record<string, boolean>;
  optional_setting_count: number;
  quality_tier: "CORE" | "ENRICHED" | "DETAILED";
  issues: WorldValidationIssue[];
  ready_for_publish: boolean;
  evaluated_at: string;
};

export type WorldCreatorContext = {
  world: WorldRead;
  membership_role: "owner" | "editor";
  readiness: WorldReadiness;
};

export type OwnerControlledProfileWrite = {
  display_name: string;
  avatar_url: string;
  intro: string;
  role_key: string | null;
  preferred_address: string;
  interests: string[];
  background: string;
};

export type OwnerControlledIdentityRead = {
  schema_version: "owner-controlled-world-character-v1";
  world_character_id: string;
  world_id: string;
  character_id: string;
  control_mode: "owner_controlled";
  status: string;
  autonomous_enabled: false;
  version: number;
  profile: OwnerControlledProfileWrite;
};

export type WorldGenerationContext = Omit<
  WorldDefinition,
  "visibility" | "join_policy"
> & {
  world_id: string;
  definition_version: number;
  contract_version: string;
  contract_hash: string;
};

export type WorldDraftCreate = WorldDefinition & {
  idempotency_key: string;
};

export type WorldUpdate = Partial<WorldDefinition> & {
  row_version: number;
};
