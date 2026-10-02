"use client";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { InlineError } from "@/components/ui/feedback";
import { useRuntimeMediaUrl } from "@/hooks/use-runtime-media-url";
import { discardDraft, preflightImage, uploadImage } from "../api/media-client";
import styles from "./media-settings.module.css";

type Selection = { id: string; url: string; allowed: boolean };
export function ImagePicker({ scopeKind, scopeId, value, onChange, disabled = false, requireRecognition = false, onBusyChange }: {
  scopeKind: "character" | "thread" | "world"; scopeId: string; value: Selection | null;
  onChange: (value: Selection | null) => void; disabled?: boolean; requireRecognition?: boolean; onBusyChange?: (value: boolean) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const selected = useRef(value);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { selected.current = value; }, [value]);
  useEffect(() => () => { controller.current?.abort(); }, []);
  const url = useRuntimeMediaUrl(value?.url);
  async function choose(file: File) {
    controller.current?.abort();
    const operation = new AbortController(); controller.current = operation;
    setBusy(true); onBusyChange?.(true); setError(null);
    let assetId: string | null = null;
    try {
      const asset = await uploadImage(file, scopeKind, scopeId, operation.signal); assetId = asset.id;
      const state = requireRecognition ? await preflightImage(asset.id, operation.signal) : { allowed: true, reason: null };
      if (operation.signal.aborted) { await discardDraft(asset.id); return; }
      const old = selected.current;
      onChange({ id: asset.id, url: asset.url, allowed: state.allowed });
      if (old && old.id !== asset.id) void discardDraft(old.id).catch(() => undefined);
      if (!state.allowed) setError(`이미지를 인식할 수 없습니다. 이미지 인식 설정을 확인하거나 사진을 제거해 주세요. (${state.reason})`);
    } catch (reason) {
      if (assetId) void discardDraft(assetId).catch(() => undefined);
      if (!operation.signal.aborted) setError(reason instanceof Error ? reason.message : "사진을 첨부하지 못했습니다.");
    } finally {
      if (controller.current === operation) { setBusy(false); onBusyChange?.(false); }
      if (input.current) input.current.value = "";
    }
  }
  return <div className={styles.picker}>
    <label className={styles.fileLabel}>이미지 1장 첨부<input aria-label="첨부 이미지 선택" ref={input} type="file" accept="image/png,image/jpeg,image/webp" disabled={disabled || busy} onChange={event => { const file = event.target.files?.[0]; if (file) void choose(file); }} /></label>
    {busy ? <p role="status">사진을 업로드하고 확인하는 중…</p> : null}
    {/* Authenticated object URLs must preserve pixels in Next and static runtimes. */}
    {/* eslint-disable-next-line @next/next/no-img-element */}
    {url ? <img src={url} alt="선택한 첨부 이미지 미리보기" className={styles.preview} /> : null}
    {value ? <Button type="button" variant="ghost" disabled={disabled || busy} onClick={() => { void discardDraft(value.id).catch(() => undefined); onChange(null); setError(null); }}>사진 제거</Button> : null}
    {error ? <InlineError>{error}{requireRecognition ? <a href="/settings">이미지 인식 설정 열기</a> : null}</InlineError> : null}
  </div>;
}
