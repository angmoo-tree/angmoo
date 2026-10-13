"use client";
import { Activity } from "lucide-react";
import { useCallback, useState } from "react";
import { SettingsCard } from "@/components/ui/settings-card";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/form-controls";
import { useUiText } from "@/hooks/use-ui-text";
import { useActiveScopedRead } from "@/hooks/use-active-scoped-read";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { getActivityRuntime, setActivityEngine, type EngineScope, type SupportedActivityEngine } from "../api/personalized-activity";
const ENGINES = { current: "기존 활동 방식", personalized_graph_v2: "기억을 반영하는 활동 방식 (V2)" };
const SOURCES: Record<string, string> = { character: "캐릭터 설정", world: "World 기본값", global: "전체 기본값", default: "초기 기본값" };
const SCOPES = { character: "이 캐릭터", world: "이 World의 기본값", global: "모든 World의 기본값" };
const TRANSITIONS = { pending_settlement: "이전 활동의 실행권과 결과 확인이 필요합니다. 확인 전에는 새 활동을 겹쳐 시작하지 않습니다.", needs_preparation: "이전 활동은 종료됐으며, 승인된 설정과 일과 준비를 확인한 뒤 새 방식으로 전환합니다.", pending_conversion: "새 방식으로 전환할 준비가 됐습니다. 다음 실행 진입에서 설정을 확인합니다.", ready: "새 활동 방식으로 실행할 수 있습니다." };
export function PersonalizedActivityPanel({ worldId, actorId, onlyCharacter = false, elevated = false }: {
    worldId: string;
    actorId: string;
    onlyCharacter?: boolean;
    elevated?: boolean;
}) {
    const t = useUiText("characters"), [scope, setScope] = useState<EngineScope>("character");
    const [choice, setChoice] = useState<SupportedActivityEngine | "inherit">("inherit"), [busy, setBusy] = useState(false), [failed, setFailed] = useState(false);
    const load = useCallback(async (signal: AbortSignal) => { const value = await getActivityRuntime(worldId, actorId, signal); if (value.world_id !== worldId || value.world_character_id !== actorId)
        throw new Error("activity_scope_invalid"); return value; }, [worldId, actorId]);
    const { data, error, refresh } = useActiveScopedRead({ scopeKey: `${worldId}:${actorId}`, active: true, read: load });
    async function save() {
        if (!data || busy)
            return;
        const auth = captureAuthRequestScope();
        setBusy(true);
        setFailed(false);
        try {
            await setActivityEngine(worldId, actorId, onlyCharacter ? "character" : scope, choice === "inherit" ? null : choice, data.policies[onlyCharacter ? "character" : scope].version);
            if (isCurrentAuthRequestScope(auth))
                refresh();
        }
        catch {
            if (isCurrentAuthRequestScope(auth))
                setFailed(true);
        }
        finally {
            if (isCurrentAuthRequestScope(auth))
                setBusy(false);
        }
    }
    return <SettingsCard elevated={elevated} title={t("활동 방식")} description={t("이 캐릭터에 적용할 활동 방식을 선택해요.")} icon={<Activity size={20}/>}>
    {data ? <>
      <p>{t(ENGINES[data.effective.engine])} · {t(SOURCES[data.effective.source] ?? "설정 확인 필요")}</p>
      {data.transition && data.transition.state !== "ready" ? <p role="status">{t(TRANSITIONS[data.transition.state])}</p> : null}
      {data.control_mode === "autonomous" ? <fieldset disabled={busy} className="grid gap-3">
        {!onlyCharacter ? <Field label={t("적용 범위")}>{props => <Select {...props} value={scope} onChange={event => setScope(event.target.value as EngineScope)}>
          {Object.entries(SCOPES).map(([value, label]) => <option key={value} value={value}>{t(label)}</option>)}
        </Select>}</Field> : null}
        <Field label={t("사용할 방식")}>{props => <Select {...props} value={choice} onChange={event => setChoice(event.target.value as SupportedActivityEngine | "inherit")}>
          <option value="inherit">{t("기본값 따르기")}</option>
          <option value="personalized_graph_v2">{t(ENGINES.personalized_graph_v2)}</option>
        </Select>}</Field>
        <p>{t("저장된 활동 방식")} · {data.policies[scope].engine ? t(ENGINES[data.policies[scope].engine!]) : t("기본값 따르기")}</p>
        <Button loading={busy} onClick={() => void save()}>{t("활동 방식 저장")}</Button>
      </fieldset> : null}
    </> : <p role="status">{t("설정 확인 중")}</p>}
    {error || failed ? <><p role="alert">{t("저장하지 못했습니다. 다른 곳에서 설정이 바뀌었는지 새로고침한 뒤 다시 시도해 주세요.")}</p><Button variant="ghost" onClick={refresh}>{t("다시 시도")}</Button></> : null}
  </SettingsCard>;
}
