import type { WorldCharacterDashboardItem } from "../types/world-character-dashboard";
import type { WorldCharacterManagementView } from "../types/world-character-management";
import type { StatusChipTone } from "@/components/ui/status";

export function parseWorldCharacterManagementView(value: string | null): WorldCharacterManagementView {
  return value === "status" || value === "settings" ? value : "profile";
}

export function sortWorldCharactersForDashboard(items: WorldCharacterDashboardItem[]) {
  return [...items].sort((a, b) => {
    const rank = (item: WorldCharacterDashboardItem) => item.profile.control_mode === "owner_controlled" ? -1 : item.autonomous_enabled ? 0 : 1;
    return rank(a) - rank(b)
      || latestWorldActivity(b) - latestWorldActivity(a)
      || a.profile.display_name.localeCompare(b.profile.display_name, "ko")
      || a.profile.world_character_id.localeCompare(b.profile.world_character_id);
  });
}

function latestWorldActivity(item: WorldCharacterDashboardItem) {
  const value = item.recent_activity?.occurred_at;
  if (!value) return 0;
  const timestamp = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`).getTime();
  return Number.isFinite(timestamp) ? timestamp : 0;
}

export function presentWorldCharacterState(item: WorldCharacterDashboardItem): { label: string; tone: StatusChipTone } {
  if (item.profile.control_mode === "owner_controlled") return { label: "World 사용자 표시", tone: "neutral" };
  if (!item.autonomous_enabled) return { label: "자율활동 꺼짐", tone: "disabled" };
  if (["running", "busy", "working"].includes(item.status.state)) return { label: "ON · 활동 중", tone: "running" };
  if (["resting", "outside_hours", "waiting_hours"].includes(item.status.state) || item.status.reason === "outside_active_hours") return { label: "ON · 활동 시간 대기", tone: "waiting" };
  if (["failed", "error", "unhealthy", "recovery_required"].includes(item.status.state)) return { label: "ON · 실행 확인 필요", tone: "danger" };
  if (item.next_activity_at && ["scheduled", "ready", "waiting"].includes(item.status.state)) return { label: "ON · 다음 활동 대기", tone: "healthy" };
  return { label: "ON · 실행 대기", tone: "waiting" };
}

export function worldCharacterRestrictionMessage(reason: string | null) {
  if (["setup_required", "not_ready", "activity_profile_required"].includes(reason ?? "")) return "이 World의 활동 준비를 완료해주세요.";
  if (["busy", "capacity_unavailable", "resource_busy", "waiting_capacity"].includes(reason ?? "")) return "서버 자원을 기다리고 있어요.";
  if (["binding_mismatch", "world_binding_mismatch", "world_scope_conflict"].includes(reason ?? "")) return "이 World의 활동 연결을 확인해주세요.";
  return "현재 이 동작을 사용할 수 없어요.";
}
