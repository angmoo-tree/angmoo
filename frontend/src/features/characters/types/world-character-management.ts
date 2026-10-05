import type { WorldCharacterDashboardItem, WorldCharacterCapabilities } from "./world-character-dashboard";
import type { AgentRunRead } from "./agents";

export type WorldCharacterManagementView = "profile" | "status" | "settings";

export type WorldCharacterManagementRead = {
  contract_version: "world-character-management-v1";
  world_id: string;
  world_character_id: string;
  character_id: string;
  item: WorldCharacterDashboardItem;
  can_manage: boolean;
};

export type WorldCharacterProfileValues = {
  display_name: string;
  handle: string | null;
  intro: string;
  avatar_url: string | null;
  banner_url: string | null;
};

export type WorldCharacterSettingsValues = {
  personality: string;
  speech_style: string;
  worldview: string;
  character_background: string;
  topic_preferences: string;
  safety_rules: string;
  active_hours_start: string;
  active_hours_end: string;
  activity_interval_minutes: number;
  max_posts_per_day: number;
  max_comments_per_day: number;
  generation_model?: string | null;
  image_model?: string | null;
  image_style?: string | null;
  appearance_prompt?: string | null;
};

export type WorldCharacterSettingsRead = {
  contract_version: "world-character-settings-v1";
  world_id: string;
  world_character_id: string;
  revision: number;
  profile: WorldCharacterProfileValues;
  settings: WorldCharacterSettingsValues;
  capabilities: WorldCharacterCapabilities;
  supported_generation_models: WorldCharacterModelOption[];
  supported_image_models: WorldCharacterModelOption[];
};

export type WorldCharacterModelOption = { value: string; label: string; enabled: boolean; reason: string | null };

export type WorldCharacterRunNowRead = {
  contract_version: "world-character-run-now-v1";
  world_id: string;
  world_character_id: string;
  character_id: string;
  revision: number;
  run: AgentRunRead;
};
