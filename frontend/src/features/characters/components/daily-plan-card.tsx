"use client";
import { CalendarDays } from "lucide-react";
import { SettingsCard } from "@/components/ui/settings-card";
import { Button } from "@/components/ui/button";
import { useUiDateFormatter } from "@/hooks/use-ui-date-formatter";
import { useUiText } from "@/hooks/use-ui-text";
import type { DailyPreparationRead, DailyActivityPlanRead } from "../api/world-activity-runtime";
const STATES = { pending: "오늘 일과 준비 전", running: "오늘 일과 만드는 중", waiting: "다시 시도할 때까지 대기", ready: "오늘 일과 준비됨", failed: "오늘 일과 생성 실패", needs_user_action: "오늘 일과 다시 만들기 필요" };
const PARTS = [["dawn", "새벽", "00:00–06:00"], ["morning", "오전", "06:00–12:00"], ["afternoon", "오후", "12:00–18:00"], ["evening", "저녁", "18:00–00:00"]] as const;
const ITEM_STATES: Record<string, string> = { planned: "예정", active: "진행 중", completed: "완료", skipped: "시간이 지나 실행하지 않음", interrupted: "중단", cancelled: "취소" };
export function DailyPlanCard({ status, plan, busy, canGenerate, onGenerate, onRefresh, elevated = false }: {
  status: DailyPreparationRead | null; plan: DailyActivityPlanRead | null; busy: boolean; canGenerate: boolean; onGenerate: () => void; onRefresh: () => void; elevated?: boolean;
}) {
  const uiText = useUiText("characters"), formatDate = useUiDateFormatter();
  return <SettingsCard elevated={elevated} title={uiText("오늘 하루 계획")} description={uiText("오늘의 활동 방향과 시간대별 계획을 확인해요.")} icon={<CalendarDays size={20} />}>
    <p role="status">{status ? `${status.local_date} · ${uiText(STATES[status.plan_state])}` : uiText("준비 상태 확인 중")}</p>
    {status?.reason_code ? <p>{uiText("현재 일과를 준비하지 못했습니다. 모델·키와 World 설정을 확인한 후 다시 만들어 주세요.")}</p> : null}
    {status?.request_state === "failed" && status.plan_state === "ready" ? <p>{uiText("다시 만들기에 실패했습니다. 기존의 유효한 오늘 일과를 계속 사용합니다.")}</p> : null}
    {status?.next_retry_at ? <p>{uiText("다음 재시도:")}{formatDate(status.next_retry_at)}</p> : null}
    {plan ? <ul className="grid gap-3">{PARTS.map(([part, label, window]) => {
      const item = plan.items.find(row => row.daypart === part);
      return item ? <li key={item.id} className="min-w-0 rounded-xl bg-surface-muted p-4"><h3 className="font-bold">{uiText(label)} · {window}</h3><p className="break-words">{item.title}</p>
        <p className="break-words text-text-secondary">{item.activity_seed}</p><p>{uiText(ITEM_STATES[item.status] ?? "확인 필요")}</p></li> : null;
    })}</ul> : null}
    <div className="flex flex-wrap gap-2"><Button loading={busy} disabled={!status || !canGenerate || status.plan_state === "running"} onClick={onGenerate}>{uiText("오늘 일과 다시 만들기")}</Button>
      <Button variant="ghost" disabled={busy} onClick={onRefresh}>{uiText("상태 새로고침")}</Button></div>
    <p className="text-sm text-text-secondary">{uiText("다시 만들기는 AI를 호출합니다. 완료된 일과와 확정 약속은 보존하며 자율활동을 자동으로 켜지 않습니다.")}</p>
  </SettingsCard>;
}
