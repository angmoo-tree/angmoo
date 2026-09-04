"use client";

import { useEffect, useRef, useState } from "react";
import { Button, Field, Input, Select } from "@/shared/ui/public";
import { getMemoryBatchSetting, MemoryApiError, retryMemoryBatch, saveMemoryBatchSetting } from "../api/memory-client";
import type { MemoryBatchSetting, MemoryBatchUpdate } from "../model/memory-batch-contract";
import styles from "./memory-workspace.module.css";

type Props = { worldId: string; subjectId: string; disabled: boolean; acquire: () => boolean; release: () => void; onCompleted: () => void };
const labels: Record<MemoryBatchSetting["status"], string> = {
  disabled: "AI 기억 정리 사용 안 함", paused: "기억 정리 일시 중지", waiting: "예약 또는 종료를 기다리고 있어요",
  running: "기억을 정리하고 있어요", pending: "다음 실행에서 이어 정리합니다", attention: "설정 확인 또는 다시 시도가 필요해요", completed: "정리를 마쳤어요. 보관할 경험이 없으면 새 기억은 생기지 않습니다.",
};

export function MemoryBatchControls({ worldId, subjectId, disabled, acquire, release, onCompleted }: Props) {
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

  useEffect(() => {
    active.current = true;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const value = await getMemoryBatchSetting(worldId, subjectId, controller.signal);
        if (controller.signal.aborted) return;
        setSaved(value);
        setDraft((current) => current ?? value);
        if (completion.current !== undefined && completion.current !== value.last_completed_at) onCompleted();
        completion.current = value.last_completed_at;
        timer = setTimeout(refresh, 5_000);
      } catch (error) {
        if (controller.signal.aborted) return;
        setNotice(error instanceof MemoryApiError && error.status === 404 ? "이 범위의 기억 설정을 사용할 수 없어요." : "기억 정리 설정을 불러오지 못했어요.");
        setFailed(true);
      }
    }
    void refresh();
    return () => { active.current = false; controller.abort(); clearTimeout(timer); };
  }, [worldId, subjectId, revision, onCompleted]);

  function change(patch: Partial<MemoryBatchSetting>) {
    setDraft((current) => current ? { ...current, ...patch } : current);
    pending.current = null;
    setNotice(""); setFailed(false);
  }

  async function save(retry = false) {
    if (!draft || !acquire()) return;
    setBusy(true); setNotice(""); setFailed(false);
    try {
      let value: MemoryBatchSetting;
      if (retry) {
        retryKey.current ??= crypto.randomUUID();
        value = await retryMemoryBatch(worldId, subjectId, retryKey.current);
        retryKey.current = null;
      } else {
        pending.current ??= {
          ai_enabled: draft.ai_enabled, shutdown_enabled: draft.shutdown_enabled, schedule_enabled: draft.schedule_enabled,
          local_time: draft.local_time, model_id: draft.model_id,
          expected_version: draft.version, expected_profile_version: draft.profile_version,
          consent_version: draft.ai_enabled && (consent || saved?.ai_enabled) ? "memory-selection-consent.v1" : null,
          idempotency_key: crypto.randomUUID(),
        };
        value = await saveMemoryBatchSetting(worldId, subjectId, pending.current);
        pending.current = null;
      }
      if (!active.current) return;
      setSaved(value); setDraft(value);
      setNotice(retry ? "다시 정리하도록 요청했어요." : "기억 정리 설정을 저장했어요. 저장만으로 AI를 호출하지 않습니다.");
    } catch (error) {
      if (!active.current) return;
      const conflict = error instanceof MemoryApiError && error.status === 409;
      setNotice(conflict ? "설정이 다른 곳에서 바뀌었어요. 최신 값을 확인한 뒤 다시 저장해 주세요." : "저장하지 못했어요. 쪽지용 AI 설정과 선택한 모델을 확인해 주세요.");
      setFailed(true);
      if (conflict) { pending.current = null; setDraft(null); setRevision((value) => value + 1); }
    } finally { if (active.current) setBusy(false); release(); }
  }

  return <section className={styles.batchControls} aria-label="기억 정리 예약">
    <h2>기억 정리</h2>
    <p>경험은 먼저 저장하고, AI가 예약 시각이나 앱 전체 종료 때 오래 보관할 기억을 고릅니다.</p>
    {!draft || !saved ? <Button variant="secondary" compact disabled={disabled} onClick={() => setRevision((value) => value + 1)}>{failed ? "설정 다시 불러오기" : "설정 불러오는 중"}</Button> : <>
      <p role="status">{labels[saved.status]} · 정리 대기 {saved.pending_count}개</p>
      {!saved.memory_enabled ? <p>기억이 꺼져 있어 자동 정리가 멈춰 있습니다. 기존 기록은 보존됩니다.</p> : null}
      <fieldset disabled={disabled || busy}>
        <label className={styles.batchCheck}><input type="checkbox" checked={draft.ai_enabled} onChange={(event) => change({ ai_enabled: event.target.checked })} />AI 선별·정리 사용</label>
        <Field label="기억 정리 모델 · 이 설치의 모든 캐릭터 공통" helperText="쪽지용 API 설정을 사용합니다. 모델 변경은 다른 캐릭터의 다음 기억 정리에도 적용됩니다.">{(props) => <Select {...props} value={draft.model_id ?? ""} onChange={(event) => change({ model_id: event.target.value || null })}><option value="">모델을 선택해 주세요</option>{saved.available_models.map((model) => <option value={model} key={model}>{model}</option>)}</Select>}</Field>
        {draft.ai_enabled && !saved.ai_enabled ? <label className={styles.batchCheck}><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} />선택한 모델로 경험의 발췌가 전송되고 API 비용이 발생할 수 있음에 동의합니다.</label> : null}
        <label className={styles.batchCheck}><input type="checkbox" checked={draft.shutdown_enabled} onChange={(event) => change({ shutdown_enabled: event.target.checked })} />앱을 완전히 종료할 때 정리</label>
        <label className={styles.batchCheck}><input type="checkbox" checked={draft.schedule_enabled} onChange={(event) => change({ schedule_enabled: event.target.checked })} />매일 정해진 시각에 정리</label>
        <Field label={`예약 시각 · ${saved.timezone}`} helperText="이 World의 시간대입니다. 앱이 꺼져 있으면 다음 실행에서 이어 처리합니다.">{(props) => <Input {...props} type="time" value={draft.local_time} onChange={(event) => change({ local_time: event.target.value })} required />}</Field>
      </fieldset>
      <p>다음 예약: {saved.next_due_at ? displayTime(saved.next_due_at, saved.timezone) : "예약 없음"}</p>
      {saved.last_completed_at ? <p>마지막 정리: {displayTime(saved.last_completed_at, saved.timezone)}</p> : null}
      <Button compact disabled={disabled || (draft.ai_enabled && (!draft.model_id || (!saved.ai_enabled && !consent)))} loading={busy} loadingLabel="저장 중" onClick={() => void save()}>정리 설정 저장</Button>
      {saved.status === "attention" && saved.ai_enabled && saved.memory_enabled ? <Button compact variant="secondary" disabled={disabled} onClick={() => void save(true)}>실패한 정리 다시 시도</Button> : null}
    </>}
    {notice ? <p role={failed ? "alert" : "status"}>{notice}</p> : null}
  </section>;
}

function displayTime(value: string, timezone: string) {
  const instant = /(?:Z|[+-]\d\d:\d\d)$/.test(value) ? value : `${value}Z`;
  return new Intl.DateTimeFormat("ko-KR", { timeZone: timezone, dateStyle: "medium", timeStyle: "short" }).format(new Date(instant));
}
