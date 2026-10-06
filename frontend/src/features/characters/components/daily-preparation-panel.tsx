"use client";
import { useUiDateFormatter } from "@/hooks/use-ui-date-formatter";

import { useUiText } from "@/hooks/use-ui-text";


import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { InlineError } from "@/components/ui/feedback";
import { ActivityCredentialForm } from "@/features/characters/components/activity-credential-form";
import { ActiveHoursControl, getActiveHoursValidation } from "@/features/characters/components/activity-hours-control";
import { PersonalizedActivityPanel } from "@/features/characters/components/personalized-activity-panel";
import { activateAgent, deactivateAgent, getAgent, updateAgentSettings } from "@/features/characters/api/agents";
import { getDailyPreparation, getDailyActivityPlan, regenerateDailyPreparation, updateActivityRuntimeMode, type ActivityRuntimeMode, type DailyPreparationRead, type DailyActivityPlanRead } from "@/features/characters/api/world-activity-runtime";
import type { AgentDetailRead } from "@/features/characters/types/agents";

const states = { pending: "오늘 일과 준비 전", running: "오늘 일과 만드는 중", waiting: "다시 시도할 때까지 대기", ready: "오늘 일과 준비됨", failed: "오늘 일과 생성 실패", needs_user_action: "오늘 일과 다시 만들기 필요" };
const parts = [ ["dawn", "새벽", "00:00–06:00"], ["morning", "오전", "06:00–12:00"], ["afternoon", "오후", "12:00–18:00"], ["evening", "저녁", "18:00–00:00"] ];
const itemStates: Record<string, string> = { planned: "예정", active: "진행 중", completed: "완료", skipped: "시간이 지나 실행하지 않음", interrupted: "중단", cancelled: "취소" };

// LOCAL: payload-backed state, existing primitives; one surface for Next/static.
export function DailyPreparationPanel({ initialAgent, initialRuntimeMode, worldId, actorId, worldName, timezone, children }: {
  initialAgent: AgentDetailRead; initialRuntimeMode: ActivityRuntimeMode; worldId: string; actorId: string; worldName: string; timezone: string; children: ReactNode;
}) {
  const formatDate = useUiDateFormatter();
  const uiText = useUiText("characters");
  const [agent, setAgent] = useState(initialAgent);
  const [runtimeMode, setRuntimeMode] = useState(initialRuntimeMode);
  const [status, setStatus] = useState<DailyPreparationRead | null>(null);
  const [plan, setPlan] = useState<DailyActivityPlanRead | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [hours, setHours] = useState([agent.settings.active_hours_start, agent.settings.active_hours_end]);
  const active = useRef(true);
  const request = useRef<string | null>(null);
  const locked = useRef(false);
  const characterId = agent.character.id;
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  useEffect(() => {
    const controller = new AbortController();
    async function refresh() {
      try {
        const next = await getDailyPreparation(characterId, worldId, controller.signal);
        const nextPlan = await getDailyActivityPlan(characterId, worldId);
        if (controller.signal.aborted) return;
        setStatus(next); setPlan(nextPlan); setError(null);
      } catch { if (!controller.signal.aborted) setError(uiText("준비 상태를 읽지 못했습니다. 새로고침해 주세요.")); }
    }
    void refresh();
    const interval = setInterval(() => void refresh(), 15000);
    return () => { controller.abort(); clearInterval(interval); };
  }, [characterId, worldId, revision, uiText]);

  async function mutate(action: "plan" | "toggle" | "hours" | "runtime") {
    if (locked.current) return;
    locked.current = true; setBusy(true); setError(null);
    try {
      if (action === "plan") {
        request.current ??= crypto.randomUUID();
        const next = await regenerateDailyPreparation(characterId, worldId, request.current, plan?.version);
        request.current = null;
        if (active.current) setStatus(next);
      } else if (action === "toggle") {
        const next = await (agent.settings.auto_enabled ? deactivateAgent(characterId) : activateAgent(characterId));
        if (active.current) setAgent(next);
      } else if (action === "runtime") {
        const result = await updateActivityRuntimeMode(characterId, worldId, "routine_resident_v1");
        const next = await getAgent(characterId);
        if (active.current) { setRuntimeMode(result.activity_runtime_mode); setAgent(next); }
      } else {
        await updateAgentSettings(characterId, { active_hours_start: hours[0], active_hours_end: hours[1] });
        const next = await getAgent(characterId); if (active.current) setAgent(next);
      }
      if (active.current) setRevision(value => value + 1);
    } catch (reason) {
      if (active.current) setError(reason instanceof Error ? uiText(reason.message) : uiText("처리하지 못했습니다. 상태를 확인해 주세요."));
    } finally { locked.current = false; if (active.current) setBusy(false); }
  }

  return <div className="space-y-6 p-4" data-product-content="daily-preparation">
    <header className="space-y-2"><h1 className="text-2xl font-bold text-text-strong">{agent.character.name} {uiText("· 활동 준비")}</h1>
      <p className="text-text-secondary">{worldName} · {timezone}</p>
      <p className="text-text-default">{agent.character.one_liner || agent.character.name}</p>
    </header>
    <section className="space-y-4 rounded-2xl border border-border-default bg-surface p-5">
      <ActivityCredentialForm characterId={characterId} hasCredential={Boolean(agent.credential?.enabled)} onSaved={async () => { const next = await getAgent(characterId); if (active.current) setAgent(next); }} />
      <ActiveHoursControl start={hours[0]} end={hours[1]} timeZone={timezone} onChange={(start, end) => setHours([start, end])} />
      <Button variant="secondary" disabled={busy || !getActiveHoursValidation(hours[0], hours[1]).valid} onClick={() => void mutate("hours")}>{uiText("활동 시간 저장")}</Button>
      {runtimeMode === "legacy_resident_v1" ? <div className="space-y-2">
        <p className="text-sm text-text-secondary">{uiText("이 캐릭터는 이전 호환 활동 방식을 사용하고 있습니다. 오늘 일과를 자동으로 준비하려면 일과 활동 방식으로 변경해 주세요. 변경해도 자율활동 켜짐·꺼짐은 유지됩니다.")}</p>
        <Button variant="secondary" disabled={busy} onClick={() => void mutate("runtime")}>{uiText("일과 활동 방식 사용")}</Button>
      </div> : <p className="text-sm text-text-secondary">{uiText("실행하면 활동 시간에 맞춰 오늘의 큰 일과 4개를 자동으로 준비합니다. 처음에는 추천 주제도 함께 만듭니다. 생성과 SNS 활동에 설정한 API 키를 사용합니다.")}</p>}
      <Button loading={busy} disabled={!agent.settings.auto_enabled && (!agent.credential?.enabled || !agent.activity_profile_readiness.ready)} onClick={() => void mutate("toggle")}>{agent.settings.auto_enabled ? uiText("자율활동 끄기") : uiText("자율활동 시작")}</Button>
      <p role="status">{uiText("자율활동 {{state}}", {state: agent.settings.auto_enabled ? uiText("켜짐") : uiText("꺼짐")})}</p>
    </section>
    {error && <InlineError>{error}</InlineError>}
    <section className="space-y-4 rounded-2xl border border-border-default bg-surface p-5" aria-busy={busy}>
      <h2 className="text-lg font-bold text-text-strong">{uiText("오늘 하루 계획")}</h2>
      <p role="status">{status ? `${status.local_date} · ${uiText(states[status.plan_state])}` : uiText("준비 상태 확인 중")}</p>
      {status?.reason_code && <p className="text-sm text-text-secondary">{uiText("현재 일과를 준비하지 못했습니다. 모델·키와 World 설정을 확인한 후 다시 만들어 주세요. (")}{status.reason_code})</p>}
      {status?.request_state === "failed" && status.plan_state === "ready" && <p className="text-sm text-text-secondary">{uiText("다시 만들기에 실패했습니다. 기존의 유효한 오늘 일과를 계속 사용합니다. (")}{status.request_reason_code})</p>}
      {status?.next_retry_at && <p className="text-sm text-text-secondary">{uiText("다음 재시도:")}{formatDate(status.next_retry_at)}</p>}
      <p className="text-sm text-text-secondary">{uiText("계획은 활동 방향입니다. 실제 장면과 게시글은 활동할 때 만들어집니다. 지난 시간대는 실제로 수행한 일이 아닙니다.")}</p>
      {plan && <ul className="space-y-3">{parts.map(([key, label, window]) => {
        const item = plan.items.find(value => value.daypart === key);
        return item ? <li key={item.id} className="rounded-xl bg-surface-muted p-3"><h3 className="font-bold">{label} · {window}</h3><p>{item.title}</p><p className="text-sm text-text-secondary">{item.activity_seed}</p><p className="text-sm">{uiText(itemStates[item.status] ?? item.status)}</p></li> : null;
      })}</ul>}
      <div className="flex flex-wrap gap-2"><Button loading={busy} disabled={!status || !agent.credential?.enabled || status.plan_state === "running"} onClick={() => void mutate("plan")}>{uiText("오늘 일과 다시 만들기")}</Button>
        <Button variant="ghost" disabled={busy} onClick={() => setRevision(value => value + 1)}>{uiText("상태 새로고침")}</Button></div>
      <p className="text-xs text-text-secondary">{uiText("다시 만들기는 AI를 호출합니다. 완료된 일과와 확정 약속은 보존하며 자율활동을 자동으로 켜지 않습니다.")}</p>
    </section>
    {children}
    <PersonalizedActivityPanel worldId={worldId} actorId={actorId} />
  </div>;
}
