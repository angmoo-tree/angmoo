import type { WorldCharacterPublicProfile } from "./world-character-profile";

export type WorldCharacterCapabilities = {
  can_activate: boolean;
  can_deactivate: boolean;
  can_run_now: boolean;
  can_edit_profile: boolean;
  can_edit_settings: boolean;
  can_view_graph: boolean;
  reason: string | null;
};

export type WorldCharacterActivitySettings = {
  active_hours_start: string;
  active_hours_end: string;
  timezone: string;
  activity_interval_minutes: number;
  max_posts_per_day: number;
  max_comments_per_day: number;
};

export type WorldCharacterDashboardItem = {
  profile: WorldCharacterPublicProfile;
  revision: number;
  autonomous_enabled: boolean;
  status: { state: string; reason: string | null };
  settings: WorldCharacterActivitySettings | null;
  next_activity_at: string | null;
  recent_activity: {
    action_type: string;
    occurred_at: string;
    post_id: string | null;
    title: string | null;
  } | null;
  capabilities: WorldCharacterCapabilities;
};

export type WorldCharacterDashboardRead = {
  contract_version: "world-character-dashboard-v1";
  world_id: string;
  summary: { total: number; enabled: number; disabled: number; users: number };
  items: WorldCharacterDashboardItem[];
};
