import type { DailyActivityPlanRead, DailyPreparationRead } from "../api/world-activity-runtime";

export const DAYPARTS = [["dawn", "새벽", "00:00–06:00"], ["morning", "오전", "06:00–12:00"], ["afternoon", "오후", "12:00–18:00"], ["evening", "저녁", "18:00–00:00"]] as const;
export const PLAN_STATES = { pending: "오늘 일과 준비 전", running: "오늘 일과 만드는 중", waiting: "다시 시도할 때까지 대기", ready: "오늘 일과 준비됨", failed: "오늘 일과 생성 실패", needs_user_action: "오늘 일과 다시 만들기 필요" };
export const PLAN_ITEM_STATES: Record<string, string> = { planned: "예정", active: "진행 중", completed: "완료", skipped: "시간이 지나 실행하지 않음", interrupted: "중단", cancelled: "취소" };

export function worldLocalDate(timezone: string, now = new Date()): string | null {
  try {
    const parts = new Intl.DateTimeFormat("en", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(now);
    const value = (name: string) => parts.find(part => part.type === name)?.value;
    return `${value("year")}-${value("month")}-${value("day")}`;
  } catch { return null; }
}

export function dailyPlanPresentation(status: DailyPreparationRead, plan: DailyActivityPlanRead | null, worldId: string, actorId: string, now = new Date()) {
  if (status.world_character_id !== actorId || (plan && (plan.world_id !== worldId || plan.world_character_id !== actorId))) return "inconsistent";
  if (!plan) return "none";
  const today = worldLocalDate(plan.timezone_name, now);
  if (!today) return "inconsistent";
  if (plan.local_date !== today) return "previous";
  if (status.local_date !== today || status.plan_id !== plan.id || status.plan_version !== plan.version) return "inconsistent";
  return "ready";
}

/** Locate the next World date boundary, including DST, without browser-zone assumptions. */
export function nextWorldDateBoundary(timezone: string, now = Date.now()): number | null {
  const date = worldLocalDate(timezone, new Date(now));
  if (!date) return null;
  let high = now + 30 * 60 * 60 * 1000, low = now;
  if (worldLocalDate(timezone, new Date(high)) === date) return null;
  while (high - low > 1000) { const middle = Math.floor((high + low) / 2); if (worldLocalDate(timezone, new Date(middle)) === date) low = middle; else high = middle; }
  return high + 1000;
}
