"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form-controls";
import { useUiText } from "@/hooks/use-ui-text";
import { useUiDateFormatter } from "@/hooks/use-ui-date-formatter";
import { useProductLeaveGuard } from "@/hooks/use-product-leave-guard";
import { getMemoryProcessing, saveMemoryProcessing, savePendingMemories, commandMemoryProcessing, MemoryApiError } from "../api/memory-client";
import type { MaintenanceAction } from "../types/consolidation-contract";
import type { MemoryProcessingSetting, MemoryProcessingUpdate, MemorySaveRequest } from "../types/memory-processing-contract";
import styles from "./memory-workspace.module.css";
import { MemoryUnsavedExperiencesControls } from "./memory-unsaved-experiences";

const editable = (value: MemoryProcessingSetting) => ({ daily_enabled: value.daily_enabled,
  local_time: value.local_time, shutdown_apply_enabled: value.shutdown_apply_enabled });
const labels: Record<MemoryProcessingSetting["status"], string> = {
  idle: "활동에서 접수한 경험은 예약 시각이나 앱 종료 때 저장해요.",
  accepted: "기억 저장을 기다리고 있어요.", applying: "접수한 경험을 기억으로 저장하고 있어요.",
  saved: "기억 저장을 마쳤어요. 검색 자료는 이어서 준비합니다.",
  partial_error: "일부 경험을 저장하지 못했어요. 저장된 기억은 유지됩니다.",
  closed: "완료된 결과와 실패 이력을 보존하고 종료했습니다.",
  cancelled: "남은 정리를 중단했습니다. 완료된 결과는 유지됩니다.",
};
type Props = { worldId: string; subjectId: string; disabled: boolean;
  acquire: () => boolean; release: () => void; onCompleted: () => void };

export function MemoryProcessingControls({ worldId, subjectId, disabled, acquire, release, onCompleted }: Props) {
  const uiText = useUiText("memory"), formatDate = useUiDateFormatter();
  const [saved, setSaved] = useState<MemoryProcessingSetting | null>(null);
  const [draft, setDraft] = useState<ReturnType<typeof editable> | null>(null);
  const [busy, setBusy] = useState<"save" | "settings" | "command" | null>(null);
  const [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [conflict, setConflict] = useState<MemoryProcessingSetting | null>(null);
  const [revision, setRevision] = useState(0);
  const lifetime = useRef<AbortController | null>(null), lock = useRef(false), generation = useRef(0);
  const pending = useRef<MemorySaveRequest | null>(null), update = useRef<MemoryProcessingUpdate | null>(null);
  const recovery = useRef<{mode: MaintenanceAction; key: string; revision: number; runId: string} | null>(null);
  const baseline = useRef<MemoryProcessingSetting | null>(null), completion = useRef<string | null | undefined>(undefined);
  const draftRef = useRef<typeof draft>(null);
  function changeDraft(value: NonNullable<typeof draft>) { draftRef.current = value; setDraft(value); }
  const dirty = Boolean(saved && draft && JSON.stringify(editable(saved)) !== JSON.stringify(draft));
  const running = saved?.status === "accepted" || saved?.status === "applying";
  const saveAvailable = Boolean(saved?.memory_enabled && saved.pending_count > 0 && !running);
  useProductLeaveGuard(dirty || busy !== null);

  useEffect(() => {
    const controller = new AbortController(); lifetime.current = controller;
    return () => controller.abort();
  }, [worldId, subjectId]);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      const started = generation.current;
      try {
        const value = await getMemoryProcessing(worldId, subjectId, controller.signal, pending.current?.idempotency_key);
        if (controller.signal.aborted || lock.current || started !== generation.current) return;
        if (pending.current && value.resolved_request_key === pending.current.idempotency_key) {
          pending.current = null; setError("");
        }
        const previous = baseline.current;
        setSaved(value);
        if (draftRef.current === null || (previous && JSON.stringify(draftRef.current) === JSON.stringify(editable(previous)))) {
          draftRef.current = editable(value); setDraft(draftRef.current); baseline.current = value;
        }
        if (completion.current !== undefined && completion.current !== value.last_applied_at) onCompleted();
        completion.current = value.last_applied_at;
      } catch {
        if (!controller.signal.aborted) setError(uiText("기억 저장 상태를 불러오지 못했어요."));
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(poll, 3000);
      }
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [worldId, subjectId, revision, onCompleted, uiText]);

  async function perform(kind: "save" | "settings") {
    if (!saved || !draft || lock.current || disabled || (kind === "save" && !saveAvailable) || (kind === "settings" && conflict) || !acquire()) return;
    lock.current = true; generation.current += 1;
    const signal = lifetime.current?.signal;
    setBusy(kind); setError(""); setNotice("");
    try {
      let value: MemoryProcessingSetting;
      if (kind === "save") {
        pending.current ??= { expected_version: saved.version, idempotency_key: crypto.randomUUID() };
        value = await savePendingMemories(worldId, subjectId, pending.current, signal);
        pending.current = null;
      } else {
        update.current ??= { ...draft, expected_version: baseline.current?.version ?? saved.version, idempotency_key: crypto.randomUUID() };
        value = await saveMemoryProcessing(worldId, subjectId, update.current, signal);
        update.current = null;
      }
      if (signal?.aborted) return;
      setSaved(value);
      if (kind === "settings") { changeDraft(editable(value)); baseline.current = value; }
      setNotice(uiText(kind === "settings" ? "기억 저장 설정을 저장했어요." : value.result === "empty" ? "지금 저장할 경험이 없어요." : "기억 저장을 요청했어요."));
    } catch (reason) {
      if (signal?.aborted) return;
      if (reason instanceof MemoryApiError && reason.status === 409) {
        pending.current = null; update.current = null;
        const latest = await getMemoryProcessing(worldId, subjectId, signal).catch(() => null);
        if (signal?.aborted) return;
        if (latest) { setSaved(latest); if (kind === "settings") setConflict(latest); }
        setError(uiText("설정이 변경됐어요. 최신 설정을 확인한 뒤 다시 요청해 주세요."));
      } else setError(uiText("기억 저장 요청을 완료하지 못했어요. 다시 누르면 같은 요청을 확인합니다."));
    } finally {
      lock.current = false; release();
      if (!signal?.aborted) setBusy(null);
    }
  }

  async function recover(mode: MaintenanceAction) {
    if (!saved?.run_id || lock.current || disabled || !acquire()) return;
    lock.current = true; generation.current += 1;
    const signal = lifetime.current?.signal;
    setBusy("command"); setError("");
    if (recovery.current?.mode !== mode || recovery.current?.runId !== saved.run_id)
      recovery.current = {mode, key: crypto.randomUUID(), revision: saved.revision ?? 0, runId: saved.run_id};
    const request = recovery.current;
    try {
      const value = await commandMemoryProcessing(worldId, subjectId, request.runId,
        {mode, idempotency_key: request.key, expected_revision: request.revision}, signal);
      if (!signal?.aborted) { setSaved(value); recovery.current = null; }
    } catch {
      if (!signal?.aborted) setError(uiText("복구 요청을 완료하지 못했어요. 상태를 확인한 뒤 다시 시도해 주세요."));
    } finally {
      lock.current = false; release(); if (!signal?.aborted) setBusy(null);
    }
  }

  if (!saved || !draft) return <div role="status"><p>{error || uiText("설정 불러오는 중")}</p>
    {error && <Button compact variant="secondary" onClick={() => setRevision(v => v + 1)}>{uiText("설정 다시 불러오기")}</Button>}</div>;
  return <div className="grid gap-4" data-memory-processing>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p role="status">{uiText("저장 대기 {{count}}개", { count: saved.pending_count })}</p>
      <Button disabled={disabled || busy !== null || !saveAvailable} loading={busy === "save"}
        loadingLabel={uiText("요청 중")} onClick={() => void perform("save")}>{uiText("지금 기억 저장")}</Button>
    </div>
    <p role="status">{uiText(["idle", "saved"].includes(saved.status) && saved.pending_count === 0 && saved.blocked_count === 0
      ? "현재 저장하지 못한 경험이나 저장 대기가 없어요." : labels[saved.status])}</p>
    <div className="flex flex-wrap gap-2">{saved.actions?.map(mode => <Button key={mode} variant="secondary"
      disabled={disabled || busy !== null} onClick={() => void recover(mode)}>{uiText(({
        resume_storage: "받은 결과 저장 재개", regenerate_failed: "실패한 부분 다시 판단", resume_remaining: "남은 작업 재개",
        cancel_remaining: "남은 정리 중단", close_without_retry: "재시도 없이 종료"})[mode])}</Button>)}</div>
    <MemoryUnsavedExperiencesControls worldId={worldId} subjectId={subjectId} processing={saved}
      disabled={disabled || busy !== null} acquire={acquire} release={release} onCompleted={onCompleted} onProcessing={setSaved} />
    <fieldset disabled={disabled || busy !== null} className="grid gap-3">
      <label className={styles.batchCheck}><input type="checkbox" checked={draft.daily_enabled} onChange={event => { update.current = null; changeDraft({ ...draft, daily_enabled: event.target.checked }); }} />{uiText("매일 정해진 시각에 기억 저장")}</label>
      <Field label={uiText("예약 시각 · {{value0}}", { value0: saved.timezone })} helperText={uiText("부하가 한 번에 몰리지 않도록 기억 정리와 일일 관계 정리는 시간을 띄워 예약하는 것을 권장해요. 실행 시각은 직접 설정할 수 있어요.")}>{props => <Input {...props} type="time" required value={draft.local_time} onChange={event => { update.current = null; changeDraft({ ...draft, local_time: event.target.value }); }} />}</Field>
      <label className={styles.batchCheck}><input type="checkbox" checked={draft.shutdown_apply_enabled} onChange={event => { update.current = null; changeDraft({ ...draft, shutdown_apply_enabled: event.target.checked }); }} />{uiText("앱을 완전히 종료할 때 기억 저장")}</label>
    </fieldset>
    <p>{uiText("다음 예약:")}{saved.next_due_at ? formatDate(saved.next_due_at) : uiText("예약 없음")}</p>
    {saved.last_applied_at && <p>{uiText("마지막 기억 저장:")}{formatDate(saved.last_applied_at)}</p>}
    {conflict && <div role="alert"><p>{uiText("다른 곳에서 같은 항목을 변경했어요. 최신 값을 확인한 뒤 저장해주세요.")}</p>
      <p>{uiText("매일 정해진 시각에 기억 저장")}: {conflict.daily_enabled ? uiText("켜짐") : uiText("꺼짐")} · {conflict.local_time} · {uiText("앱을 완전히 종료할 때 기억 저장")}: {conflict.shutdown_apply_enabled ? uiText("켜짐") : uiText("꺼짐")}</p>
      <Button variant="secondary" onClick={() => { baseline.current = conflict; setConflict(null); }}>{uiText("최신 값을 확인했어요. 내 입력 유지")}</Button></div>}
    <Button disabled={disabled || !dirty || Boolean(conflict)} loading={busy === "settings"} loadingLabel={uiText("저장 중")} onClick={() => void perform("settings")}>{uiText("기억 저장 설정 저장")}</Button>
    {notice && <p role="status">{notice}</p>}{error && <p role="alert">{error}</p>}
  </div>;
}
