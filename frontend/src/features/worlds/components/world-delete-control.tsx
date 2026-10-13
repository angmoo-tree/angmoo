"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/form-controls";
import { ChevronDown } from "lucide-react";
import { useUiText } from "@/hooks/use-ui-text";
import { useAuthRuntimeIdentity } from "@/hooks/use-auth-runtime-identity";
import { deleteWorld, previewWorldDeletion } from "../api/world-deletion";
import { WorldApiError } from "../api/worlds";
import type { WorldDeletionCommand, WorldDeletionPreview, WorldDeletionReceipt } from "../types/world-deletion";
import styles from "./world-delete-control.module.css";

type DeleteControlProps = {
  worldId: string; canDelete?: boolean; isDefaultSpace?: boolean;
  onAccepted?: (receipt: WorldDeletionReceipt) => void;
  renderExport?: (worldId: string) => ReactNode;
};

export function WorldDeleteControl(props: DeleteControlProps) {
  const identity = useAuthRuntimeIdentity(props.worldId);
  return <ScopedDeleteControl key={identity} {...props} />;
}

function ScopedDeleteControl({ worldId, canDelete, isDefaultSpace, onAccepted, renderExport }: DeleteControlProps) {
  const text = useUiText("worlds");
  const [preview, setPreview] = useState<WorldDeletionPreview | null>(null);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [consent, setConsent] = useState(false);
  const [pending, setPending] = useState(false);
  const [confirmationLocked, setConfirmationLocked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const focusFrame = useRef<number | null>(null);
  const controller = useRef<AbortController | null>(null);
  const command = useRef<WorldDeletionCommand | null>(null);
  useEffect(() => () => { controller.current?.abort(); if (focusFrame.current !== null) cancelAnimationFrame(focusFrame.current); }, []);
  useEffect(() => {
    // A fresh confirmation starts at the target, not the previous export scroll.
    if (open && content.current?.parentElement) content.current.parentElement.scrollTop = 0;
  }, [open]);
  function close() {
    if (pending) return;
    setOpen(false);
    focusFrame.current = requestAnimationFrame(() => trigger.current?.focus());
  }
  async function show() {
    if (command.current) { setOpen(true); return; }
    const abort = new AbortController(); controller.current?.abort(); controller.current = abort;
    setPending(true); setError(null);
    try {
      const value = await previewWorldDeletion(worldId, abort.signal);
      if (abort.signal.aborted) return;
      setPreview(value); setOpen(true); setName(""); setConsent(false); setConfirmationLocked(false); command.current = null;
    } catch {
      if (!abort.signal.aborted) setError("삭제 상태를 확인하지 못했어요.");
    } finally { if (!abort.signal.aborted) setPending(false); }
  }
  async function apply() {
    if (!preview?.can_delete || pending) return;
    const body = command.current ?? { expected_row_version: preview.row_version, confirmed_name: name, consent: true as const, idempotency_key: crypto.randomUUID() };
    command.current = body; // Response loss replays this exact command, never a new key.
    setConfirmationLocked(true);
    const abort = new AbortController(); controller.current?.abort(); controller.current = abort;
    setPending(true); setError(null);
    try {
      const receipt = await deleteWorld(worldId, body, abort.signal);
      if (abort.signal.aborted) return;
      setOpen(false); onAccepted?.(receipt);
    } catch (reason) {
      if (reason instanceof WorldApiError && reason.status >= 400 && reason.status < 500) { command.current = null; setConfirmationLocked(false); }
      if (!abort.signal.aborted) setError(reason instanceof WorldApiError && reason.message === "row_version_conflict"
        ? "World 내용이 바뀌었어요. 현재 내용을 확인한 뒤 다시 삭제해주세요." : "삭제 상태를 확인하지 못했어요.");
    } finally { if (!abort.signal.aborted) setPending(false); }
  }
  return <>
    {isDefaultSpace ? <span>{text("기본 SNS World는 삭제할 수 없어요.")}</span> : <Button ref={trigger} variant="danger" disabled={canDelete !== true || pending} onClick={() => void show()}>{text("World 삭제")}</Button>}
    {!open && error ? <p role="status">{text(error)}</p> : null}
    <Dialog open={open} onOpenChange={value => { if (!value) close(); }} title={text("이 World를 영구 삭제할까요?")} className={styles.dialog}
      initialFocusRef={cancel} closeOnEscape={!pending} closeOnBackdrop={!pending}
      closeButtonAttributes={{ disabled: pending }}
      actions={<><Button ref={cancel} variant="secondary" disabled={pending} onClick={close}>{text("취소")}</Button>
        <Button variant="danger" loading={pending} disabled={!preview?.can_delete || name !== preview.stored_name || !consent} onClick={() => void apply()}>{text("영구 삭제")}</Button></>}>
      <div ref={content} className={styles.content}>
        <div className={styles.target}>
          <p className={styles.targetLabel}>{text("삭제할 World")}</p>
          <p className={styles.worldName}>{preview?.stored_name}</p>
          <p className={styles.warning}>{text("삭제가 시작되면 되돌릴 수 없어요.")}</p>
        </div>
        <dl className={styles.scope}>
          <div>
            <dt>{text("삭제되는 정보")}</dt>
            <dd>{text("이 World의 설정, 캐릭터 등록·현재 설정·활동, 게시글, 채팅, 관계, 기억과 첨부 자료")}</dd>
          </div>
          <div>
            <dt>{text("유지되는 정보")}</dt>
            <dd>{text("캐릭터의 첫 등록 원본과 재사용에 필요한 초기 이미지·연결, 다른 World의 자료와 공용 설정")}</dd>
          </div>
        </dl>
        <Field label={text("확인을 위해 World 이름을 입력해주세요.")} helperText={text("위에 표시된 이름을 정확히 입력해주세요.")} required>
          {field => <Input {...field} type="text" autoComplete="off" spellCheck={false} placeholder={text("World 이름")}
            value={name} disabled={pending || confirmationLocked} onChange={event => setName(event.target.value)} />}
        </Field>
        <label className={styles.consent}>
          <input type="checkbox" checked={consent} disabled={pending} onChange={event => setConsent(event.target.checked)} />
          <span>{text("영구 삭제를 확인했어요.")}</span>
        </label>
        {error ? <p className={styles.error} role="status">{text(error)}</p> : null}
        {preview?.export_available && renderExport ? <details key={`export-${open}`} className={styles.export}>
          <summary><span>{text("삭제 전 패키지 내보내기 (선택)")}</span><ChevronDown size={18} aria-hidden="true" /></summary>
          <p className={styles.exportHint}>{text("패키지 내보내기는 World 구성을 보관하는 기능이며, 전체 활동 기록 백업은 아니에요.")}</p>
          {renderExport(worldId)}
        </details> : null}
      </div>
    </Dialog>
  </>;
}
