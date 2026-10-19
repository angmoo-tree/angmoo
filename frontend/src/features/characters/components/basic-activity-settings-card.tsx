"use client";
import { useCallback, useEffect, useEffectEvent, useRef, useState } from "react";
import { Settings2 } from "lucide-react";
import { SettingsCard } from "@/components/ui/settings-card";
import { Button } from "@/components/ui/button";
import { useUiText } from "@/hooks/use-ui-text";
import { useActiveScopedRead } from "@/hooks/use-active-scoped-read";
import { useProductLeaveGuard } from "@/hooks/use-product-leave-guard";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { readBasicActivitySettings, saveBasicActivitySettings, toggleBasicActivity, type ActivityPolicy, type BasicActivitySettings } from "../api/basic-activity-settings";
import { ActivityPolicyFields, POLICY_KEYS, validActivityPolicy } from "./activity-policy-fields";
import type { ActivityActivation } from "../types/activity-activation";

const REASONS: Record<string, string> = {
  world_not_published: "World를 개시한 뒤 자율활동을 켤 수 있어요.",
  credential_required: "SNS 활동 키와 모델을 먼저 저장해주세요.",
  world_activity_policy_invalid: "활동 시간과 작성 한도를 확인해주세요.",
  activity_maintenance: "현재 활동 실행을 준비 중이에요.",
};
type EditorState = { dirty: boolean; busy: boolean };
type Props = { worldId: string; actorId: string; revision: number; onEditorState?: (value: EditorState) => void; onMutation?: () => void; showActivation?: boolean; onActivationChange?: (value: ActivityActivation | null) => void };

export function BasicActivitySettingsCard({ worldId, actorId, revision, onEditorState, onMutation, showActivation = true, onActivationChange }: Props) {
  const t = useUiText("characters");
  const load = useCallback((signal: AbortSignal) => readBasicActivitySettings(worldId, actorId, signal), [worldId, actorId]);
  const read = useActiveScopedRead({ scopeKey: `${worldId}:${actorId}`, active: true, read: load });
  const previousRevision = useRef(revision);
  const refresh = useEffectEvent(read.refresh);
  useEffect(() => {
    if (previousRevision.current !== revision) { previousRevision.current = revision; refresh(); }
  }, [revision]);
  return (
    <SettingsCard elevated title={t("활동 설정")} description={t("활동 시간, 허용 행동, 작성 상한을 설정해요.")} icon={<Settings2 size={20} />}>
      {read.data ? <BasicActivityEditor key={read.identity} data={read.data} refresh={read.refresh} onEditorState={onEditorState} onMutation={onMutation} showActivation={showActivation} onActivationChange={onActivationChange} available={!read.error && !read.loading} /> : <p role="status">{t("설정 확인 중")}</p>}
      {read.error ? <><p role="alert">{t("활동 설정을 불러오지 못했어요.")}</p><Button variant="ghost" onClick={read.refresh}>{t("다시 시도")}</Button></> : null}
    </SettingsCard>
  );
}

function BasicActivityEditor({ data, refresh, onEditorState, onMutation, showActivation, onActivationChange, available }: {
  data: BasicActivitySettings; refresh: () => void; onEditorState?: (value: EditorState) => void; onMutation?: () => void;
  showActivation: boolean; onActivationChange?: (value: ActivityActivation | null) => void; available: boolean;
}) {
  const t = useUiText("characters");
  const [baseline, setBaseline] = useState(data.policy), [draft, setDraft] = useState(data.policy);
  const [busy, setBusy] = useState(false), [failed, setFailed] = useState(false), [conflict, setConflict] = useState(false), [saved, setSaved] = useState(false);
  const request = useRef<AbortController | null>(null);
  const dirty = POLICY_KEYS.some(key => !Object.is(draft[key], baseline[key]));
  const releaseSavedGuard = useProductLeaveGuard(dirty || busy);
  const notify = useEffectEvent((value: EditorState) => onEditorState?.(value));
  useEffect(() => { notify({ dirty, busy }); }, [dirty, busy]);
  const activationNotify = useEffectEvent((value: ActivityActivation | null) => onActivationChange?.(value));
  useEffect(() => () => { request.current?.abort(); notify({ dirty: false, busy: false }); activationNotify(null); }, []);
  const reconcile = useEffectEvent((next: ActivityPolicy) => {
    const unedited = POLICY_KEYS.filter(key => Object.is(draft[key], baseline[key]));
    const changes = Object.fromEntries(unedited.map(key => [key, next[key]]));
    setDraft(current => ({ ...current, ...changes }));
    setBaseline(current => ({ ...current, ...changes }));
  });
  useEffect(() => {
    let current = true;
    queueMicrotask(() => { if (current) reconcile(data.policy); });
    return () => { current = false; };
  }, [data.policy]);

  async function perform(action: (signal: AbortSignal) => Promise<void>) {
    if (request.current) return false;
    const scope = captureAuthRequestScope(), controller = new AbortController();
    request.current = controller; setBusy(true); onEditorState?.({ dirty, busy: true }); setFailed(false); setConflict(false);
    const current = () => !controller.signal.aborted && isCurrentAuthRequestScope(scope);
    try { await action(controller.signal); return current(); }
    catch { if (current()) setFailed(true); return false; }
    finally { if (current()) { request.current = null; setBusy(false); onEditorState?.({ dirty, busy: false }); if (!dirty) releaseSavedGuard(); } }
  }
  const enableRequest = useRef<() => Promise<boolean>>(async () => false);
  useEffect(() => { enableRequest.current = async () => {
    if (!available || request.current) return false;
    if (data.autonomous_enabled) return true;
    if (!data.can_activate) return false;
    return perform(async signal => {
      try { await toggleBasicActivity(data.world_id, data.world_character_id, data.revision, true, signal); if (!signal.aborted) onMutation?.(); }
      finally { if (!signal.aborted) refresh(); }
    });
  }; });
  useEffect(() => {
    activationNotify({ enabled: data.autonomous_enabled, canEnable: available && (data.autonomous_enabled || data.can_activate), busy, reason: data.reason, enable: () => enableRequest.current() });
  }, [available, data.autonomous_enabled, data.can_activate, data.reason, busy]);
  async function save(signal: AbortSignal) {
    if (!dirty || !validActivityPolicy(draft)) return;
    const latest = await readBasicActivitySettings(data.world_id, data.world_character_id, signal);
    const keys = POLICY_KEYS.filter(key => !Object.is(draft[key], baseline[key]));
    if (keys.some(key => !Object.is(latest.policy[key], baseline[key]) && !Object.is(latest.policy[key], draft[key]))) {
      if (!signal.aborted) { setConflict(true); refresh(); }
      return;
    }
    const result = await saveBasicActivitySettings(data.world_id, data.world_character_id, latest.revision, Object.fromEntries(keys.map(key => [key, draft[key]])), signal);
    if (!signal.aborted) { setBaseline(result.policy); setDraft(result.policy); setSaved(true); onMutation?.(); refresh(); }
  }
  return <>
    <p role="status">{t(data.autonomous_enabled ? "자율활동 ON" : "자율활동 OFF")} · {data.timezone}</p>
    {showActivation ? <Button variant="secondary" loading={busy} disabled={data.autonomous_enabled ? !data.can_deactivate : !data.can_activate}
      onClick={() => void perform(async signal => {
        try { await toggleBasicActivity(data.world_id, data.world_character_id, data.revision, !data.autonomous_enabled, signal); if (!signal.aborted) onMutation?.(); }
        finally { if (!signal.aborted) refresh(); }
      })}>
      {t(data.autonomous_enabled ? "자율활동 끄기" : "자율활동 켜기")}
    </Button> : null}
    {!data.can_activate && data.reason ? <p>{t(REASONS[data.reason] ?? "현재 자율활동을 켤 수 없어요. 설정과 준비 상태를 확인해주세요.")}</p> : null}
    <form className="grid gap-4" onSubmit={event => { event.preventDefault(); void perform(save); }}>
      <ActivityPolicyFields value={draft} disabled={busy} onChange={changes => { setDraft(current => ({ ...current, ...changes })); setSaved(false); setConflict(false); }} />
      <div className="flex flex-wrap gap-3">
        <Button variant="secondary" disabled={!dirty || busy} onClick={() => { setBaseline(data.policy); setDraft(data.policy); setSaved(false); setConflict(false); }}>{t("변경 취소")}</Button>
        <Button type="submit" loading={busy} disabled={!dirty || !validActivityPolicy(draft)}>{t("설정 저장")}</Button>
      </div>
    </form>
    {saved ? <p role="status">{t("설정을 저장했어요.")}</p> : null}
    {conflict ? <div role="alert">
      <p>{t("같은 항목이 다른 곳에서 변경되었어요. 입력을 보존했으니 최신 값과 확인해주세요.")}</p>
      <Button variant="secondary" onClick={() => { setBaseline(data.policy); setConflict(false); }}>{t("최신 값을 확인했어요. 내 입력 유지")}</Button>
    </div> : null}
    {failed ? <><p role="alert">{t("저장하지 못했어요. 입력을 보존했으니 최신 설정을 확인해주세요.")}</p><Button variant="ghost" onClick={refresh}>{t("다시 시도")}</Button></> : null}
  </>;
}
