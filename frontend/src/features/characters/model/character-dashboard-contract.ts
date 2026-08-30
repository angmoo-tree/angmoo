import type { StatusChipTone } from "@/shared/ui/public";

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

const FAILED_SLOT_STATES = new Set([
  "failed",
  "unhealthy",
  "recovery_required",
  "error",
]);
const RUNNING_SLOT_STATES = new Set(["running", "busy", "working"]);

export function presentCharacterAutonomy(
  item: CharacterDashboardItem,
  mutation: CharacterAutonomyMutationState | null,
): CharacterAutonomyPresentation {
  if (item.character.execution_mode === "local") {
    return {
      actionLabel: null,
      actionVariant: null,
      label: "외부 연결",
      state: "external",
      tone: "neutral",
    };
  }
  if (mutation === "activating") {
    return {
      actionLabel: "키는 중...",
      actionVariant: "primary",
      label: "켜는 중",
      state: "activating",
      tone: "running",
    };
  }
  if (mutation === "deactivating") {
    return {
      actionLabel: "끄는 중...",
      actionVariant: "strong",
      label: "끄는 중",
      state: "deactivating",
      tone: "running",
    };
  }
  if (!item.settings.auto_enabled) {
    return {
      actionLabel: "켜기",
      actionVariant: "primary",
      label: "자율활동 꺼짐",
      state: "off",
      tone: "disabled",
    };
  }
  const slotStatus = item.assigned_slot?.status.trim().toLowerCase() ?? "";
  if (
    item.assigned_slot?.last_error ||
    FAILED_SLOT_STATES.has(slotStatus)
  ) {
    return {
      actionLabel: "끄기",
      actionVariant: "strong",
      label: "실행 확인 필요",
      state: "failed",
      tone: "danger",
    };
  }
  if (RUNNING_SLOT_STATES.has(slotStatus)) {
    return {
      actionLabel: "끄기",
      actionVariant: "strong",
      label: "활동 중",
      state: "running",
      tone: "running",
    };
  }
  if (!item.activity_summary.within_active_hours) {
    return {
      actionLabel: "끄기",
      actionVariant: "strong",
      label: "활동 시간 밖",
      state: "resting",
      tone: "waiting",
    };
  }
  if (item.activity_summary.next_activity_at) {
    return {
      actionLabel: "끄기",
      actionVariant: "strong",
      label: "다음 활동 대기",
      state: "scheduled",
      tone: "healthy",
    };
  }
  return {
    actionLabel: "끄기",
    actionVariant: "strong",
    label: "자율활동 켜짐",
    state: "ready",
    tone: "healthy",
  };
}

export function summarizeCharacterAutonomy(items: CharacterDashboardItem[]) {
  return items.reduce(
    (summary, item) => {
      summary.total += 1;
      if (item.character.execution_mode === "local") {
        summary.external += 1;
      } else if (item.settings.auto_enabled) {
        summary.enabled += 1;
      } else {
        summary.disabled += 1;
      }
      return summary;
    },
    { total: 0, enabled: 0, disabled: 0, external: 0 },
  );
}

export function sortCharactersForDashboard(items: CharacterDashboardItem[]) {
  return [...items].sort((a, b) => {
    const autonomyDiff = autonomyRank(a) - autonomyRank(b);
    if (autonomyDiff !== 0) return autonomyDiff;
    const recencyDiff = latestTimestamp(b) - latestTimestamp(a);
    if (recencyDiff !== 0) return recencyDiff;
    return (
      a.character.name.localeCompare(b.character.name, "ko") ||
      a.character.id.localeCompare(b.character.id)
    );
  });
}

function autonomyRank(item: CharacterDashboardItem) {
  if (item.character.execution_mode === "local") return 2;
  return item.settings.auto_enabled ? 0 : 1;
}

function latestTimestamp(item: CharacterDashboardItem) {
  const values = [
    item.assigned_slot?.last_run_at,
    item.activity_summary.last_activity_at,
    item.recent_activity[0]?.created_at,
  ];
  return Math.max(
    0,
    ...values.map((value) => {
      if (!value) return 0;
      const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value)
        ? value
        : `${value}Z`;
      const timestamp = new Date(normalized).getTime();
      return Number.isFinite(timestamp) ? timestamp : 0;
    }),
  );
}
