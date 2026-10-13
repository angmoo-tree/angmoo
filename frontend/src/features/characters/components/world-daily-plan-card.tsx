"use client";
import { useEffect, useRef, useState } from "react";
import { useProductLeaveGuard } from "@/hooks/use-product-leave-guard";
import { useUiText } from "@/hooks/use-ui-text";
import { getDailyPreparation, getDailyActivityPlan, regenerateDailyPreparation, type DailyPreparationRead, type DailyActivityPlanRead } from "../api/world-activity-runtime";
import { worldCredentialTransport } from "../api/world-credentials";
import { DailyPlanCard } from "./daily-plan-card";
export function WorldDailyPlanCard({ characterId, worldId, actorId }: { characterId: string; worldId: string; actorId: string }) {
  const uiText = useUiText("characters");
  const [status, setStatus] = useState<DailyPreparationRead | null>(null), [plan, setPlan] = useState<DailyActivityPlanRead | null>(null);
  const [hasKey, setHasKey] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState(false), [reload, setReload] = useState(0);
  const scope = `${worldId}:${actorId}`, active = useRef(scope);
  useProductLeaveGuard(busy);
  useEffect(() => {
    active.current = scope;
    const controller = new AbortController();
    void Promise.all([getDailyPreparation(characterId, worldId, controller.signal), getDailyActivityPlan(characterId, worldId, controller.signal), worldCredentialTransport(worldId, actorId, "sns").read(controller.signal)]).then(([preparation, daily, credential]) => {
      if (controller.signal.aborted || preparation.world_character_id !== actorId || daily && daily.world_character_id !== actorId) return;
      setStatus(preparation); setPlan(daily); setHasKey(credential.has_key); setError(false);
    }).catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => { controller.abort(); active.current = ""; };
  }, [worldId, actorId, characterId, scope, reload]);
  async function regenerate() {
    if (!status || busy || !hasKey) return;
    setBusy(true);
    try {
      const result = await regenerateDailyPreparation(characterId, worldId, crypto.randomUUID(), status.plan_version ?? undefined);
      if (active.current === scope && result.world_character_id === actorId) { setStatus(result); setReload(value => value + 1); }
    } catch { if (active.current === scope) setError(true); }
    finally { if (active.current === scope) setBusy(false); }
  }
  return <div>{error ? <p role="alert">{uiText("오늘 일과를 불러오거나 갱신하지 못했어요. 다시 확인해주세요.")}</p> : null}
    <DailyPlanCard elevated status={status} plan={plan} busy={busy} canGenerate={hasKey} onGenerate={() => void regenerate()} onRefresh={() => setReload(value => value + 1)} /></div>;
}
