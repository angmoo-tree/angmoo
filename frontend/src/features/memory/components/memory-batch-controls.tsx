"use client";
import { useUiDateFormatter } from "@/hooks/use-ui-date-formatter";
import { useUiNumberFormatter } from "@/hooks/use-ui-number-formatter";

import { SettingsCard } from "@/components/ui/settings-card";
import { BrainCircuit } from "lucide-react";
import { MemoryCredentialFields } from "./memory-credential-fields";
import { useUiText } from "@/hooks/use-ui-text";


import { generationProfileValue, THINKING_HELP } from "@/config/generation-profiles";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form-controls";
import { getMemoryBatchSetting, MemoryApiError, retryMemoryBatch, saveMemoryBatchSetting } from "@/features/memory/api/memory-client";
import type { MemoryBatchSetting, MemoryBatchUpdate } from "@/features/memory/types/memory-batch-contract";
import { memoryBatchFailureMessage } from "@/features/memory/utils/batch-status";
import styles from "./memory-workspace.module.css";

import { MemoryConsolidationControls } from "./memory-consolidation-controls";
import { mergeEditedValue } from "@/lib/state/edited-fields";
import { useProductLeaveGuard } from "@/hooks/use-product-leave-guard";

const editable = (value: MemoryBatchSetting) => ({ ai_enabled: value.ai_enabled, shutdown_enabled: value.shutdown_enabled,
  schedule_enabled: value.schedule_enabled, local_time: value.local_time, model_id: value.model_id, thinking_level: value.thinking_level });

type Props = { subjectName: string; scopeVersion: number; worldId: string; subjectId: string; disabled: boolean; acquire: () => boolean; release: () => void; onCompleted: () => void };
const labels: Record<MemoryBatchSetting["status"], string> = {
  capacity_blocked: "저장 한도에 도달해 기억 정리를 멈췄어요",
  disabled: "AI 기억 정리 사용 안 함", paused: "기억 정리 일시 중지", waiting: "예약 또는 종료를 기다리고 있어요",
  running: "기억을 정리하고 있어요", pending: "다음 실행에서 이어 정리합니다", attention: "지난 기억 정리를 마치지 못했어요", completed: "정리를 마쳤어요. 보관할 경험이 없으면 새 기억은 생기지 않습니다.",
};

export function MemoryBatchControls({ worldId, subjectId, subjectName, scopeVersion, disabled, acquire, release, onCompleted }: Props) {
  const formatDate = useUiDateFormatter();
  const formatNumber = useUiNumberFormatter();
  const uiText = useUiText("memory");
  const [saved, setSaved] = useState<MemoryBatchSetting | null>(null);
  const [draft, setDraft] = useState<MemoryBatchSetting | null>(null);
  const [consent, setConsent] = useState(false);
  const [notice, setNotice] = useState("");
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const pending = useRef<MemoryBatchUpdate | null>(null);
  const retryKey = useRef<string | null>(null);
  const active = useRef(true);
  const completion = useRef<string | null | undefined>(undefined);
  const baseline = useRef<MemoryBatchSetting | null>(null), saving = useRef<AbortController | null>(null);
  const [conflict, setConflict] = useState<MemoryBatchSetting | null>(null);
  const [credentialReady, setCredentialReady] = useState(false);
  const [credentialDirty, setCredentialDirty] = useState(false);
  useProductLeaveGuard(Boolean(saved && draft && JSON.stringify(editable(saved)) !== JSON.stringify(editable(draft))) || busy);
  useEffect(() => () => saving.current?.abort(), []);

  useEffect(() => {
    active.current = true;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const value = await getMemoryBatchSetting(worldId, subjectId, controller.signal);
        if (controller.signal.aborted) return;
        setSaved(value);
        baseline.current ??= value;
        setDraft((current) => current ?? value);
        if (completion.current !== undefined && completion.current !== value.last_completed_at) onCompleted();
        completion.current = value.last_completed_at;
        timer = setTimeout(refresh, 5_000);
      } catch (error) {
        if (controller.signal.aborted) return;
        setNotice(error instanceof MemoryApiError && error.status === 404 ? uiText("이 범위의 기억 설정을 사용할 수 없어요.") : uiText("기억 정리 설정을 불러오지 못했어요."));
        setFailed(true);
      }
    }
    void refresh();
    return () => { active.current = false; controller.abort(); clearTimeout(timer); };
  }, [worldId, subjectId, revision, onCompleted, uiText]);

  function change(patch: Partial<MemoryBatchSetting>) {
    setDraft((current) => current ? { ...current, ...patch } : current);
    pending.current = null;
    setNotice(""); setFailed(false);
  }

  async function save(retry = false) {
    if (!draft || conflict || !acquire()) return;
    const controller = new AbortController(); saving.current = controller;
    setBusy(true); setNotice(""); setFailed(false);
    try {
      let value: MemoryBatchSetting;
      if (retry) {
        retryKey.current ??= crypto.randomUUID();
        value = await retryMemoryBatch(worldId, subjectId, retryKey.current);
        retryKey.current = null;
      } else {
        if (!pending.current) {
          const latest = await getMemoryBatchSetting(worldId, subjectId, controller.signal);
          if (!active.current) return;
          const merged = mergeEditedValue(editable(baseline.current ?? latest), editable(latest), editable(draft));
          if (merged.conflicts.length) {
            setSaved(latest); setDraft({ ...latest, ...merged.value }); setConflict(latest);
            setNotice(uiText("다른 곳에서 같은 항목을 변경했어요. 최신 값을 확인한 뒤 저장해주세요.")); setFailed(true); return;
          }
          pending.current = { ...merged.value, expected_version: latest.version, expected_profile_version: latest.profile_version,
            consent_version: merged.value.ai_enabled && (consent || latest.ai_enabled) ? "memory-selection-consent.v1" : null,
            idempotency_key: crypto.randomUUID() };
        }
        value = await saveMemoryBatchSetting(worldId, subjectId, pending.current, controller.signal);
        pending.current = null;
      }
      if (!active.current) return;
      setSaved(value); setDraft(value);
      baseline.current = value;
      setNotice(retry ? uiText("다시 정리하도록 요청했어요.") : uiText("기억 정리 설정을 저장했어요. 저장만으로 AI를 호출하지 않습니다."));
    } catch (error) {
      if (!active.current) return;
      const conflict = error instanceof MemoryApiError && error.status === 409;
      setNotice(conflict ? uiText("설정이 다른 곳에서 바뀌었어요. 최신 값을 확인한 뒤 다시 저장해 주세요.") : uiText("저장하지 못했어요. 이 캐릭터의 기억 정리용 API 키와 모델을 확인해 주세요."));
      setFailed(true);
      if (conflict) { pending.current = null; setRevision(value => value + 1); }
    } finally { if (active.current) setBusy(false); release(); }
  }

  return <SettingsCard elevated title={uiText("기억·관계 정리")} description={uiText("지금 또는 예약 시간에 경험을 정리해요.")} icon={<BrainCircuit size={20} />}>
    <MemoryCredentialFields worldId={worldId} subjectId={subjectId} purpose="consolidation" onDirtyChange={setCredentialDirty} onMetadata={value => {
      setCredentialReady(value.has_key);
      const changes = { model_id: value.model, thinking_level: value.thinking_level === "medium" ? "medium" as const : "high" as const, profile_version: value.configuration_revision ?? 0 };
      if (baseline.current) baseline.current = { ...baseline.current, ...changes };
      setSaved(current => current ? { ...current, ...changes } : current); setDraft(current => current ? { ...current, ...changes } : current);
    }} />
    {!draft || !saved ? <Button variant="secondary" compact disabled={disabled} onClick={() => setRevision((value) => value + 1)}>{failed ? uiText("설정 다시 불러오기") : uiText("설정 불러오는 중")}</Button> : <>
      <p role="status">{uiText(labels[saved.status])} {uiText(" · 정리 대기 {{count}}개", {count: saved.pending_count})}</p>
      <p>{uiText("저장된 기억 {{count}} / {{limit}}개", {count: formatNumber(saved.stored_count), limit: formatNumber(saved.storage_limit)})}</p>
      {saved.run_saved_count !== null && saved.run_pending_count !== null ? <p>{uiText("표시 중인 정리 작업에서 저장 {{saved}}개 · 남은 경험 {{pending}}개", {saved: saved.run_saved_count, pending: saved.run_pending_count})}</p> : null}
      {saved.capacity_blocked ? <p role="status">{uiText("저장 한도에 도달해 새 기억 정리를 멈췄어요. 기존 기억은 보존됩니다. 불필요한 기억을 삭제하거나 보관 기간이 지나 공간이 생기면 남은 경험을 이어 정리합니다.")}</p> : null}
      {saved.status === "attention" ? <p role="status">{uiText(memoryBatchFailureMessage(saved.last_code))}</p> : null}
      {!saved.memory_enabled ? <p>{uiText("기억이 꺼져 있어 자동 정리가 멈춰 있습니다. 기존 기록은 보존됩니다.")}</p> : null}
      <MemoryConsolidationControls timezone={saved.timezone} key={`${worldId}:${subjectId}`} worldId={worldId} subjectId={subjectId} subjectName={subjectName}
        scopeVersion={scopeVersion} version={saved.version} profileVersion={saved.profile_version}
        disabled={disabled || busy || !saved.memory_enabled || !saved.ai_enabled || !credentialReady} dirty={credentialDirty || draft.ai_enabled !== saved.ai_enabled || draft.shutdown_enabled !== saved.shutdown_enabled || draft.schedule_enabled !== saved.schedule_enabled || draft.local_time !== saved.local_time || draft.model_id !== saved.model_id || draft.thinking_level !== saved.thinking_level}
        acquire={acquire} release={release} onCompleted={onCompleted} />
      <fieldset disabled={disabled || busy}>
        <label className={styles.batchCheck}><input type="checkbox" checked={draft.ai_enabled} onChange={(event) => change({ ai_enabled: event.target.checked })} />{uiText("AI 선별·정리 사용")}</label>

        <p>{uiText(THINKING_HELP)}</p>
        {draft.model_id && !generationProfileValue(draft.model_id, draft.thinking_level) ? <p role="alert">{uiText("기존 모델은 지원이 종료되었습니다. 모델을 다시 선택해 주세요. 저장된 API key는 유지됩니다.")}</p> : null}
        {draft.ai_enabled && !saved.ai_enabled ? <label className={styles.batchCheck}><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} />{uiText("선택한 모델로 경험의 발췌가 전송되고 API 비용이 발생할 수 있음에 동의합니다.")}</label> : null}
        <label className={styles.batchCheck}><input type="checkbox" checked={draft.shutdown_enabled} onChange={(event) => change({ shutdown_enabled: event.target.checked })} />{uiText("앱을 완전히 종료할 때 정리")}</label>
        <label className={styles.batchCheck}><input type="checkbox" checked={draft.schedule_enabled} onChange={(event) => change({ schedule_enabled: event.target.checked })} />{uiText("매일 정해진 시각에 정리")}</label>
        <Field label={uiText("예약 시각 · {{value0}}", {value0: saved.timezone})} helperText={uiText("이 World의 시간대입니다. 앱이 꺼져 있으면 다음 실행에서 이어 처리합니다.")}>{(props) => <Input {...props} type="time" value={draft.local_time} onChange={(event) => change({ local_time: event.target.value })} required />}</Field>
      </fieldset>
      <p>{uiText("다음 예약:")}{saved.next_due_at ? formatDate(saved.next_due_at) : uiText("예약 없음")}</p>
      {saved.status === "attention" && saved.next_due_at ? <p>{uiText("다음 예약은 다음 정기 정리 시각입니다. 실패한 정리는 아래에서 다시 시도할 수 있어요.")}</p> : null}
      {saved.last_completed_at ? <p>{uiText("마지막 정리:")}{formatDate(saved.last_completed_at)}</p> : null}
      {conflict ? <div role="alert"><p>{uiText("다른 곳에서 같은 항목을 변경했어요. 최신 값을 확인한 뒤 저장해주세요.")}</p><dl>{([
        ["AI 선별·정리 사용", conflict.ai_enabled ? uiText("켜짐") : uiText("꺼짐")],
        ["앱을 완전히 종료할 때 정리", conflict.shutdown_enabled ? uiText("켜짐") : uiText("꺼짐")],
        ["매일 정해진 시각에 정리", conflict.schedule_enabled ? uiText("켜짐") : uiText("꺼짐")],
        ["예약 시각", conflict.local_time], ["현재 저장된 모델", conflict.model_id ?? "—"],
      ]).map(([label, value]) => <div key={label}><dt>{uiText(label)}</dt><dd>{value}</dd></div>)}</dl><Button variant="secondary" onClick={() => { baseline.current = conflict; setConflict(null); }}>{uiText("최신 값을 확인했어요. 내 입력 유지")}</Button></div> : null}
      {draft.ai_enabled && !credentialReady ? <p>{uiText("이 용도의 API key를 먼저 등록해주세요.")}</p> : null}
      <Button compact disabled={disabled || Boolean(conflict) || (draft.ai_enabled && (!credentialReady || credentialDirty || !generationProfileValue(draft.model_id, draft.thinking_level) || (!saved.ai_enabled && !consent)))} loading={busy} loadingLabel={uiText("저장 중")} onClick={() => void save()}>{uiText("정리 설정 저장")}</Button>
      {saved.status === "attention" && saved.ai_enabled && saved.memory_enabled && saved.retryable ? <Button compact variant="secondary" disabled={disabled || !saved.can_run} onClick={() => void save(true)}>{uiText("실패한 정리 다시 시도")}</Button> : null}
    </>}
    {notice ? <p role={failed ? "alert" : "status"}>{notice}</p> : null}
  </SettingsCard>;
}
