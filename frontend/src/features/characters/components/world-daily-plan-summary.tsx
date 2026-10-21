"use client";
import { useCallback } from "react";
import { CalendarDays } from "lucide-react";
import { SettingsCard } from "@/components/ui/settings-card";
import { Button } from "@/components/ui/button";
import { useUiText } from "@/hooks/use-ui-text";
import { useActiveScopedRead } from "@/hooks/use-active-scoped-read";
import { getPreparedDailyPlan, type DailyPreparationRead, type DailyActivityPlanRead } from "../api/world-activity-runtime";
import { dailyPlanPresentation, nextWorldDateBoundary, PLAN_STATES } from "../utils/daily-plan-presentation";
import { DailyPlanRows } from "./daily-plan-rows";

type Read = { preparation: DailyPreparationRead; plan: DailyActivityPlanRead | null };
const boundary = (value: Read) => value.plan ? nextWorldDateBoundary(value.plan.timezone_name) : null;
export function WorldDailyPlanSummary({ worldId, actorId, characterId, active }: { worldId: string; actorId: string; characterId: string; active: boolean }) {
  const t = useUiText("characters");
  const load = useCallback(async (signal: AbortSignal): Promise<Read> => {
    const { preparation, plan } = await getPreparedDailyPlan(characterId, worldId, signal);
    if (preparation.world_character_id !== actorId || (plan && (plan.world_id !== worldId || plan.world_character_id !== actorId))) throw new Error("daily_plan_scope_invalid");
    return { preparation, plan };
  }, [worldId, actorId, characterId]);
  const { data, error, loading, refresh } = useActiveScopedRead({ scopeKey: `${worldId}:${actorId}:${characterId}`, active, read: load, refreshAt: boundary });
  const presentation = data ? dailyPlanPresentation(data.preparation, data.plan, worldId, actorId) : null;
  return <SettingsCard elevated iconTone="soft" title={t("오늘 하루 계획")} description={t("오늘의 시간대별 계획을 확인해요.")} icon={<CalendarDays size={20} />}>
    {error ? <p role="alert">{t(data ? "최신 정보를 확인하지 못했어요." : "정보를 불러오지 못했어요.")}</p> : null}
    {loading && !data ? <p role="status">{t("불러오는 중…")}</p> : null}
    {data ? <>
      <p role="status">{data.preparation.local_date} · {t(PLAN_STATES[data.preparation.plan_state] ?? "확인 필요")}</p>
      {data.plan ? <p className="text-sm text-text-secondary">{data.plan.timezone_name}</p> : null}
      {presentation !== "ready" ? <p>{t(presentation === "inconsistent" ? "확인 필요" : "오늘 계획이 아직 없습니다.")}</p> : null}
      {presentation === "previous" && data.plan ? <p>{t("{{date}}의 계획 · 오늘 계획이 아닙니다.", { date: data.plan.local_date })}</p> : null}
      {data.preparation.request_state === "failed" && presentation === "ready" ? <p>{t("다시 만들기에 실패했습니다. 기존의 유효한 오늘 일과를 계속 사용합니다.")}</p> : null}
      {presentation !== "inconsistent" ? <DailyPlanRows plan={data.plan} compact highlightCurrent={presentation === "ready"} /> : null}
    </> : null}
    {error || presentation === "inconsistent" ? <Button variant="secondary" onClick={refresh}>{t("다시 시도")}</Button> : null}
  </SettingsCard>;
}
