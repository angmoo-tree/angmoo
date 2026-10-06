"use client";
import { DailyPlanCard } from "./daily-plan-card";

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


// LOCAL: payload-backed state, existing primitives; one surface for Next/static.
export function DailyPreparationPanel({ initialAgent, initialRuntimeMode, worldId, actorId, worldName, timezone, children }: {
  initialAgent: AgentDetailRead; initialRuntimeMode: ActivityRuntimeMode; worldId: string; actorId: string; worldName: string; timezone: string; children: ReactNode;
}) {
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
    <DailyPlanCard status={status} plan={plan} busy={busy} canGenerate={Boolean(agent.credential?.enabled)} onGenerate={() => void mutate("plan")} onRefresh={() => setRevision(value => value + 1)} />
    {children}
    <PersonalizedActivityPanel worldId={worldId} actorId={actorId} />
  </div>;
}
