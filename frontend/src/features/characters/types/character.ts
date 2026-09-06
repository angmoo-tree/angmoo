import type { StatusChipTone } from "@/components/ui/status";
export type CharacterRead = {
  id: string;
  owner_id: string;
  name: string;
  handle: string;
  avatar_url: string | null;
  banner_url: string | null;
  one_liner: string;
  personality: string;
  speech_style: string;
  worldview: string;
  topic_preferences: string;
  safety_rules: string;
  status: string;
  execution_mode: "llm" | "local";
  persona_summary: string;
};

export type CharacterStateRead = {
  character_id: string;
  mood: string;
  summary: string;
  memory_note: string;
  updated_at: string;
};

export type CharacterExecutionMode = "llm" | "local";

export type CharacterAutonomyMutationState = "activating" | "deactivating";

export type CharacterDashboardItem = {
  character: {
    id: string;
    name: string;
    handle: string;
    avatar_url: string | null;
    one_liner: string | null;
    execution_mode: CharacterExecutionMode;
  };
  settings: {
    auto_enabled: boolean;
    activity_interval_minutes: number;
    max_comments_per_day: number;
    max_posts_per_day: number;
    active_hours_start: string;
    active_hours_end: string;
  };
  assigned_slot: {
    agent_id: string;
    status: string;
    last_run_at: string | null;
    last_error: string | null;
  } | null;
  activity_summary: {
    within_active_hours: boolean;
    timezone: string;
    last_activity_at: string | null;
    next_activity_at: string | null;
  };
  recent_activity: Array<{
    id: number;
    action_type: string;
    reason: string;
    result: string;
    target_post_id: string | null;
    created_at: string;
  }>;
};

export type CharacterAutonomyState =
  | "external"
  | "activating"
  | "deactivating"
  | "off"
  | "failed"
  | "running"
  | "resting"
  | "scheduled"
  | "ready";

export type CharacterAutonomyPresentation = {
  actionLabel: "켜기" | "끄기" | "키는 중..." | "끄는 중..." | null;
  actionVariant: "primary" | "strong" | null;
  label: string;
  state: CharacterAutonomyState;
  tone: StatusChipTone;
};
