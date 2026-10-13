"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { useUiText } from "@/hooks/use-ui-text";
import { useUiDateFormatter } from "@/hooks/use-ui-date-formatter";
import { useProductLeaveGuard } from "@/hooks/use-product-leave-guard";
import { getUnsavedExperiences, recheckUnsavedExperiences, discardUnsavedExperience, getMemoryProcessing, MemoryApiError } from "../api/memory-client";
import type { MemoryUnsavedExperiences, MemoryUnsavedExperience, MemoryProcessingSetting, MemorySaveRequest, MemoryIndividualRecheckRequest, MemoryDiscardRequest } from "../types/memory-processing-contract";
import styles from "./memory-workspace.module.css";

const reasons: Record<MemoryUnsavedExperience["reason"], string> = {
  source_changed: "입력으로 사용한 원문이 변경되어 확인할 수 없어요.",
  access_unavailable: "현재 이 경험의 출처에 접근할 수 없어요.",
  proof_unavailable: "입력과 활동 결과의 연결을 확인할 수 없어요.",
  activation_closed: "이 경험을 접수한 기억 사용 기간이 종료되었어요.",
  description_invalid: "저장할 상황 설명을 확인할 수 없어요.",
  result_invalid: "성공한 활동 결과를 확인할 수 없어요.",
  validation_failed: "이 경험을 저장하는 데 필요한 확인을 마치지 못했어요.",
};
type Intent = { kind: "recheck"; sequence?: number; data: MemorySaveRequest | MemoryIndividualRecheckRequest }
  | { kind: "discard"; sequence: number; data: MemoryDiscardRequest };
type Props = { worldId: string; subjectId: string; processing: MemoryProcessingSetting; disabled: boolean;
  acquire: () => boolean; release: () => void; onCompleted: () => void; onProcessing: (value: MemoryProcessingSetting) => void };

export function MemoryUnsavedExperiencesControls({ worldId, subjectId, processing, disabled, acquire, release, onCompleted, onProcessing }: Props) {
  const uiText = useUiText("memory"), formatDate = useUiDateFormatter();
  const [page, setPage] = useState<MemoryUnsavedExperiences | null>(null);
  const [busy, setBusy] = useState(false), [loadingMore, setLoadingMore] = useState(false);
  const [revision, setRevision] = useState(0), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [confirm, setConfirm] = useState<MemoryUnsavedExperience | null>(null);
  const [retryable, setRetryable] = useState(false);
  const pending = useRef<Intent | null>(null), lock = useRef(false), lifetime = useRef<AbortController | null>(null);
  const generation = useRef(0), cancelButton = useRef<HTMLButtonElement | null>(null);
  const heading = useRef<HTMLHeadingElement | null>(null);
  useProductLeaveGuard(busy || confirm !== null || retryable);

  useEffect(() => {
    const controller = new AbortController(); lifetime.current = controller;
    return () => { controller.abort(); generation.current += 1; if (lock.current) { lock.current = false; release(); } };
  }, [worldId, subjectId, release]);

  useEffect(() => {
    const controller = new AbortController(), started = generation.current;
    getUnsavedExperiences(worldId, subjectId, controller.signal).then(value => {
      if (!controller.signal.aborted && started === generation.current && !lock.current) setPage(value);
    }).catch(() => { if (!controller.signal.aborted && started === generation.current) setError(uiText("저장하지 못한 경험을 불러오지 못했어요.")); });
    return () => controller.abort();
  }, [worldId, subjectId, revision, processing.blocked_count, processing.scope_busy, uiText]);

  async function more() {
    if (!page?.next_cursor || loadingMore || lock.current) return;
    const started = generation.current, signal = lifetime.current?.signal;
    setLoadingMore(true);
    try {
      const next = await getUnsavedExperiences(worldId, subjectId, signal, page.next_cursor);
      if (signal?.aborted || started !== generation.current) return;
      setPage(previous => previous ? { ...next, items: [...previous.items, ...next.items.filter(row => !previous.items.some(old => old.receipt_sequence === row.receipt_sequence))] } : next);
    } catch { if (!signal?.aborted && started === generation.current) setError(uiText("저장하지 못한 경험을 불러오지 못했어요.")); }
    finally { if (!signal?.aborted) setLoadingMore(false); }
  }

  async function perform(intent: Intent) {
    if (lock.current || disabled || !acquire()) return;
    lock.current = true; generation.current += 1; pending.current = intent;
    const signal = lifetime.current?.signal;
    setBusy(true); setError(""); setNotice(""); setRetryable(false);
    try {
      if (intent.kind === "discard") {
        const value = await discardUnsavedExperience(worldId, subjectId, intent.sequence, intent.data, signal);
        if (signal?.aborted) return;
        setConfirm(null); setNotice(uiText("이 경험의 기억 저장을 포기했어요. 원래 대화와 SNS 활동은 유지됩니다."));
        onProcessing({ ...processing, pending_count: value.pending_count, blocked_count: value.blocked_count });
      } else {
        let value = await recheckUnsavedExperiences(worldId, subjectId, intent.data, signal, intent.sequence);
        while (value.status === "accepted" || value.status === "applying") {
          if (signal?.aborted) return;
          onProcessing(value); setNotice(uiText("저장하지 못한 경험을 다시 확인하고 있어요."));
          await new Promise(resolve => setTimeout(resolve, 3000));
          if (signal?.aborted) return;
          value = await getMemoryProcessing(worldId, subjectId, signal, intent.data.idempotency_key);
          if (value.resolved_request_key !== intent.data.idempotency_key) throw new MemoryApiError(502, "memory_recheck_request_unresolved");
        }
        if (signal?.aborted) return;
        if (value.run_id != null && value.run_state !== "completed") throw new MemoryApiError(503, "memory_recheck_incomplete");
        onProcessing(value);
        if (value.rejected_count === undefined || value.skipped_count === undefined) throw new MemoryApiError(502, "memory_recheck_counts_missing");
        setNotice(value.result === "empty" ? uiText("지금 다시 확인할 경험이 없어요.") : uiText("다시 확인한 결과: 저장 {{saved}}개 · 확인 실패 {{rejected}}개 · 건너뜀 {{skipped}}개", {
          saved: value.applied_count, rejected: value.rejected_count, skipped: value.skipped_count,
        }));
      }
      pending.current = null; onCompleted();
      requestAnimationFrame(() => { if (!signal?.aborted) heading.current?.focus(); });
    } catch (reason) {
      if (signal?.aborted) return;
      setNotice("");
      if (reason instanceof MemoryApiError && reason.status === 409) {
        pending.current = null; setConfirm(null);
        setError(uiText("다른 작업이 처리 중이거나 경험이 변경됐어요. 최신 상태를 확인한 뒤 다시 선택해 주세요."));
      } else { setConfirm(null); setRetryable(true); setError(uiText("요청 결과를 확인하지 못했어요. 다시 누르면 같은 요청을 확인합니다.")); }
    } finally {
      if (lock.current) { lock.current = false; release(); }
      if (!signal?.aborted) { setBusy(false); setRevision(v => v + 1); }
    }
  }

  function recheck(row?: MemoryUnsavedExperience) {
    if (pending.current) return;
    const data = { expected_version: processing.version, idempotency_key: crypto.randomUUID(),
      ...(row ? { expected_receipt_version: row.state_version } : {}) };
    void perform({ kind: "recheck", sequence: row?.receipt_sequence, data });
  }

  return <section className={styles.unsavedSection} aria-label={uiText("저장하지 못한 경험")} data-memory-unsaved>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h3 ref={heading} tabIndex={-1}>{uiText("저장하지 못한 경험 {{count}}개", { count: processing.blocked_count })}</h3>
      {processing.blocked_count > 0 && <Button compact disabled={disabled || busy || retryable || processing.can_recheck !== true} onClick={() => recheck()}>{uiText("저장하지 못한 경험 다시 확인")}</Button>}
    </div>
    {processing.blocked_count > 0 && <p>{uiText("현재 선택한 캐릭터와 World에서 저장하지 못한 경험을 다시 확인해요. 확인할 수 있는 경험만 기억으로 저장합니다.")}</p>}
    {processing.scope_busy && !busy && <p role="status">{uiText("다른 기억 저장 작업이 진행 중이에요. 가능한 동작은 각 경험에서 확인해 주세요.")}</p>}
    {page && page.items.length === 0 && <p>{uiText("저장하지 못한 경험이 없어요.")}</p>}
    {page && page.items.length > 0 && <div className={styles.unsavedScroll} tabIndex={0} role="region" aria-label={uiText("저장하지 못한 경험 목록")}>
      <ul className={styles.unsavedList}>{page.items.map(row => <li key={row.receipt_sequence} data-unsaved-experience={row.receipt_sequence}>
        <time dateTime={row.occurred_at}>{formatDate(row.occurred_at)}</time>
        <p>{row.description ?? uiText("현재 확인할 수 없는 경험이에요. 원문은 표시하지 않습니다.")}</p>
        <p className={styles.muted}>{uiText(reasons[row.reason])}</p>
        <p className={styles.muted}>{uiText("이 경험을 기억으로 저장하지 않습니다. 원래 채팅과 SNS 글은 유지됩니다.")}</p>
        <div className="flex flex-wrap gap-2">
          <Button compact variant="secondary" disabled={disabled || busy || retryable || !row.can_recheck} onClick={() => recheck(row)}>{uiText("다시 확인")}</Button>
          <Button compact variant="danger" disabled={disabled || busy || retryable || !row.can_discard} onClick={() => setConfirm(row)}>{uiText("이 경험 저장 포기")}</Button>
        </div>
      </li>)}</ul>
      {page.next_cursor && <Button compact variant="secondary" disabled={busy || loadingMore} loading={loadingMore} loadingLabel={uiText("불러오는 중")} onClick={() => void more()}>{uiText("저장하지 못한 경험 더 보기")}</Button>}
    </div>}
    {notice && <p role="status">{notice}</p>}{error && <p role="alert">{error}</p>}
    {retryable && <Button compact variant="secondary" disabled={disabled || busy} onClick={() => { if (pending.current) void perform(pending.current); }}>{uiText("같은 요청 다시 확인")}</Button>}
    {error && !retryable && <Button compact variant="secondary" disabled={busy} onClick={() => { setError(""); setRevision(v => v + 1); }}>{uiText("목록 다시 불러오기")}</Button>}
    <Dialog open={confirm !== null} title={uiText("이 경험 저장 포기")} initialFocusRef={cancelButton}
      onOpenChange={open => { if (!open && !busy) setConfirm(null); }} closeButtonAttributes={{ disabled: busy }} closeOnEscape={!busy} closeOnBackdrop={!busy}
      actions={<><Button ref={cancelButton} variant="secondary" disabled={busy} onClick={() => setConfirm(null)}>{uiText("취소")}</Button>
        <Button variant="danger" disabled={disabled || busy || retryable || !confirm?.can_discard} loading={busy} loadingLabel={uiText("요청 중")}
          onClick={() => { if (confirm) void perform({ kind: "discard", sequence: confirm.receipt_sequence, data: { expected_receipt_version: confirm.state_version, idempotency_key: crypto.randomUUID() } }); }}>{uiText("이 경험 저장 포기")}</Button></>}>
      <p>{uiText("이 경험을 기억으로 저장하는 작업을 종료합니다. 원래 대화와 SNS 활동은 유지되며, 저장 포기는 되돌릴 수 없습니다.")}</p>
      {confirm?.description && <p className={styles.dialogCopy}>{confirm.description}</p>}
    </Dialog>
  </section>;
}
