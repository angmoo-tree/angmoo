export type SocialAgentCharacterRead = {
  id: string;
  name: string;
  handle: string;
  avatar_url: string | null;
};

export type AgentActivitySettingRead = {
  auto_enabled: boolean;
};

export type AgentSlotRead = {
  status: string;
  last_error: string | null;
  last_run_at: string | null;
  heartbeat_interval_seconds: number | null;
};

export type AgentActivitySummaryRead = {
  within_active_hours: boolean;
  next_activity_at: string | null;
  today_comment_count: number;
  today_post_count: number;
  today_like_count: number;
};

export type AgentDetailRead = {
  character: SocialAgentCharacterRead;
  settings: AgentActivitySettingRead;
  assigned_slot: AgentSlotRead | null;
  activity_summary: AgentActivitySummaryRead;
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
