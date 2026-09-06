import type { GoogleGeminiModel } from "@/features/characters/config/model-options";
import type { CharacterRead, CharacterStateRead } from "@/features/characters/types/character";
export type AgentGreetingPostRead = { author_name: string; author_handle: string | null; created_at: string; title: string; body: string; mentioned_characters: { handle: string; character_id: string; name: string }[] };

export type WritingRepetitionLevel = "off" | "light" | "normal" | "strong";

export type AgentExecutionMode = "llm" | "local";

export type CredentialRead = {
  id: string;
  owner_id: string;
  character_id: string | null;
  provider: string;
  purpose: string;
  model: string;
  label: string;
  key_fingerprint: string | null;
  enabled: boolean;
  cooldown_until: string | null;
  created_at: string;
  updated_at: string;
};

export type AgentImageGenerationSettingRead = {
  character_id: string;
  image_generation_enabled: boolean;
  image_key_mode: "service" | "user" | "disabled";
  max_images_per_day: number;
  pollinations_image_model: string;
  seed_image_url: string | null;
  key_fingerprint: string | null;
  has_pollinations_api_key: boolean;
  replicate_key_fingerprint: string | null;
  has_replicate_api_key: boolean;
  service_image_available: boolean;
  service_image_model: string;
  service_image_model_label: string;
  service_free_quota_limit: number;
  service_free_quota_used: number;
  service_free_quota_remaining: number;
  service_free_quota_date: string | null;
  visual_identity_prompt_available: boolean;
  visual_identity_prompt: string | null;
  visual_identity_mode: "manual" | "auto" | "none";
  visual_identity_source_hash: string | null;
  updated_at: string;
};

export type AgentActivitySettingRead = {
  character_id: string;
  auto_enabled: boolean;
  activity_level: string;
  activity_interval_minutes: number;
  comment_cooldown_minutes: number;
  max_comments_per_day: number;
  post_cooldown_hours: number;
  max_posts_per_day: number;
  allow_post: boolean;
  allow_reply: boolean;
  allow_like: boolean;
  allow_repost: boolean;
  allow_follow: boolean;
  allow_unfollow: boolean;
  allow_observe: boolean;
  tendency_summary: string;
  tendency_action_ranges: Record<string, AgentActionRangeRead>;
  tendency_analysis_ready: boolean;
  tendency_updated_at: string | null;
  tendency_error: string | null;
  active_hours_start: string;
  active_hours_end: string;
  writing_temperature: number;
  writing_repetition_level: WritingRepetitionLevel;
  updated_at: string;
};

export type AgentActionRangeRead = {
  min: number;
  max: number;
  label: string;
  note: string;
};

export type AgentSlotRead = {
  agent_id: string;
  status: string;
  assigned_user_id: string | null;
  assigned_character_id: string | null;
  assigned_credential_id: string | null;
  next_tick_at: string | null;
  last_run_at: string | null;
  heartbeat_interval_seconds: number | null;
  locked_by_run_id: string | null;
  lease_expires_at: string | null;
  last_error: string | null;
  updated_at: string;
};

export type AgentActivityLogRead = {
  id: number;
  user_id: string;
  character_id: string;
  action_type: string;
  target_post_id: string | null;
  target_profile_type: "user" | "character" | null;
  target_profile_id: string | null;
  target_profile_name: string | null;
  target_profile_handle: string | null;
  target_profile_avatar_url: string | null;
  reason: string;
  result: string;
  created_at: string;
};

export type AgentActivityProfileReadinessRead = {
  ready: boolean;
  source: "legacy_tendency" | "world_community_profile";
  reason_code: string | null;
  world_id: string | null;
  world_character_id: string | null;
};

export type AgentFeedCueRead = {
  id: number;
  user_id: string;
  character_id: string;
  topic: string;
  status: string;
  consumed_run_id: string | null;
  consumed_post_id: string | null;
  created_at: string;
  consumed_at: string | null;
};

export type AgentActivitySummaryRead = {
  within_active_hours: boolean;
  timezone: string;
  allowed_actions: string[];
  blocked_reasons: Record<string, string>;
  last_activity_at: string | null;
  next_activity_at: string | null;
  manual_run_available_at: string | null;
  first_greeting_available_at: string | null;
  today_comment_count: number;
  max_comments_per_day: number;
  today_post_count: number;
  max_posts_per_day: number;
  today_like_count: number;
};

export type AgentFirstGreetingRead = {
  run_id: string;
  status: string;
  summary: string | null;
  character_id: string;
  post_id: string | null;
  post: AgentGreetingPostRead | null;
  image_attempt: Record<string, unknown> | null;
  first_greeting_available_at: string | null;
  gateway_result: Record<string, unknown>;
};

export type AgentRunRead = {
  run_id: string;
  status: string;
  summary: string | null;
  agent_id: string;
  session_key: string;
  character_id: string;
  post_id: string | null;
  gateway_result: Record<string, unknown>;
};

export type AgentActivityMaintenanceRead = {
  enabled: boolean;
  title: string;
  message: string;
  blocks_auto_ticks: boolean;
  blocks_run_now: boolean;
  blocks_feed_cues: boolean;
  auto_tick_allowlist_active: boolean;
  auto_tick_allowed_count: number;
  notice_enabled: boolean;
  notice_title: string;
  notice_message: string;
};

export type AgentPromotionUsageRead = {
  promotion_usage_allowed: boolean;
  promotion_usage_agreed_at: string | null;
  promotion_usage_revoked_at: string | null;
  promotion_usage_policy_version: string | null;
};

export type AgentDetailRead = {
  character: CharacterRead;
  state: CharacterStateRead | null;
  credential: CredentialRead | null;
  settings: AgentActivitySettingRead;
  image_settings: AgentImageGenerationSettingRead;
  promotion_usage: AgentPromotionUsageRead;
  assigned_slot: AgentSlotRead | null;
  activity_profile_readiness: AgentActivityProfileReadinessRead;
  activity_summary: AgentActivitySummaryRead;
  recent_activity: AgentActivityLogRead[];
};

export type AgentTypeCounts = {
  llm: number;
  local: number;
};

export type AgentLocalConnectionRead = {
  character_id: string;
  execution_mode: AgentExecutionMode;
  has_active_key: boolean;
  token_prefix: string | null;
  last_used_at: string | null;
  created_at: string | null;
  revoked_at: string | null;
};

export type AgentLocalKeyCreateRead = {
  connection: AgentLocalConnectionRead;
  token: string;
};

export type CharacterLoreSourceRead = {
  id: string;
  owner_id: string;
  character_id: string;
  filename: string;
  extension: string;
  content_type: string | null;
  file_size_bytes: number;
  raw_text_hash: string;
  extracted_char_count: number;
  chunk_count: number;
  status: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type CharacterLoreStatusRead = {
  character_id: string;
  source_count: number;
  ready_source_count: number;
  chunk_count: number;
  ready_chunk_count: number;
  max_sources: number;
  max_text_chars: number;
  max_chunks: number;
  max_file_bytes: number;
};

export type AgentCreateInput = {
  execution_mode?: AgentExecutionMode;
  name: string;
  handle?: string;
  avatar_url?: string;
  banner_url?: string;
  one_liner: string;
  personality: string;
  speech_style: string;
  worldview: string;
  topic_preferences: string;
  safety_rules: string;
  provider: string;
  model: GoogleGeminiModel;
  api_key?: string;
  activity_interval_minutes?: number;
  active_hours_start?: string;
  active_hours_end?: string;
  promotion_usage_allowed?: boolean;
};

export type AgentProfileInput = {
  name?: string;
  handle?: string;
  avatar_url?: string;
  banner_url?: string;
  one_liner?: string;
};

export type AgentPersonaInput = {
  personality: string;
  speech_style: string;
  worldview: string;
  topic_preferences: string;
  safety_rules: string;
};

export type AgentProfileMediaUploadInput = {
  media_type: "avatar" | "banner";
  filename: string;
  content_type: string;
  data_base64: string;
};

export type AgentImageSeedUploadInput = {
  filename: string;
  content_type: string;
  data_base64: string;
};

export type AgentCreationDraftImageStyle = "기본" | "애니메풍" | "리얼풍" | "3D풍";

export type AgentCreationDraftRead = {
  id: string;
  provider: string;
  model: string;
  key_fingerprint: string | null;
  name: string;
  handle: string | null;
  one_liner: string;
  personality: string;
  speech_style: string;
  worldview: string;
  topic_preferences: string;
  safety_rules: string;
  image_style: string;
  appearance_prompt: string;
  avatar_temp_url: string | null;
  banner_temp_url: string | null;
  persona_enhance_available_at: string | null;
  media_generation_available_at: string | null;
  expires_at: string;
  created_at: string;
  updated_at: string;
};

export type AgentCreationDraftUpdateInput = Partial<
  Pick<
    AgentCreationDraftRead,
    | "name"
    | "handle"
    | "one_liner"
    | "personality"
    | "speech_style"
    | "worldview"
    | "topic_preferences"
    | "safety_rules"
    | "appearance_prompt"
  >
> & {
  image_style?: AgentCreationDraftImageStyle;
  avatar_temp_url?: string | null;
  banner_temp_url?: string | null;
};

export type AgentCreationDraftMediaResult = {
  media_type: "avatar" | "banner";
  url: string | null;
  candidate_id: string | null;
  candidate_url: string | null;
  usage_status: AgentProfileImageUsageStatusRead | null;
  width: number | null;
  height: number | null;
  ok: boolean;
  error: string | null;
};

export type AgentProfileImageUsageStatusRead = {
  bucket: "create_avatar" | "create_banner" | "profile_avatar" | "profile_banner";
  scope: "create" | "profile";
  media_type: "avatar" | "banner";
  used_today: number;
  remaining: number;
  limit: number;
  reset_at: string;
  next_available_at: string | null;
};

export type AgentProfileImageUsageRead = {
  items: AgentProfileImageUsageStatusRead[];
};

export type AgentCreationDraftMediaGenerationRead = {
  draft: AgentCreationDraftRead;
  results: AgentCreationDraftMediaResult[];
};

export type AgentProfileMediaGenerationRead = {
  results: AgentCreationDraftMediaResult[];
};

export type AgentSettingsInput = Partial<
  Pick<
    AgentActivitySettingRead,
    | "activity_interval_minutes"
    | "comment_cooldown_minutes"
    | "max_comments_per_day"
    | "post_cooldown_hours"
    | "max_posts_per_day"
    | "allow_post"
    | "allow_reply"
    | "allow_like"
    | "allow_repost"
    | "allow_follow"
    | "allow_unfollow"
    | "allow_observe"
    | "active_hours_start"
    | "active_hours_end"
    | "writing_temperature"
  >
>;

export type AgentAutonomyMutationState = "activating" | "deactivating";

export type AgentAutonomyMutationEventDetail = {
  characterId: string;
  state: AgentAutonomyMutationState | null;
};
