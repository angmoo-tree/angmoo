"use client";
import { useUiText } from "@/hooks/use-ui-text";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Image as ImageIcon } from "lucide-react";
import { Button, IconButton } from "@/components/ui/button";
import { InlineError } from "@/components/ui/feedback";
import { useRuntimeMediaUrl } from "@/hooks/use-runtime-media-url";
import { discardDraft, preflightImage, uploadImage } from "../api/media-client";
import styles from "./media-settings.module.css";

type Selection = { id: string; url: string; allowed: boolean };
export function ImagePicker({ scopeKind, scopeId, value, onChange, disabled = false, requireRecognition = false, onBusyChange, renderLayout }: {
  scopeKind: "character" | "thread" | "world"; scopeId: string; value: Selection | null;
  onChange: (value: Selection | null) => void; disabled?: boolean; requireRecognition?: boolean; onBusyChange?: (value: boolean) => void;
  renderLayout?: (slots: { trigger: ReactNode; preview: ReactNode; feedback: ReactNode }) => ReactNode;
}) {
  const uiText = useUiText("media");
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
      if (!state.allowed) setError(uiText("이미지를 인식할 수 없습니다. 이미지 인식 설정을 확인하거나 사진을 제거해 주세요. ({{value0}})", {value0: state.reason ?? ""}));
    } catch (reason) {
      if (assetId) void discardDraft(assetId).catch(() => undefined);
      if (!operation.signal.aborted) setError(reason instanceof Error ? uiText(reason.message) : uiText("사진을 첨부하지 못했습니다."));
    } finally {
      if (controller.current === operation) { setBusy(false); onBusyChange?.(false); }
      if (input.current) input.current.value = "";
    }
  }
  const fileInput = <input aria-label={uiText("첨부 이미지 선택")} ref={input} type="file" accept="image/png,image/jpeg,image/webp" hidden={Boolean(renderLayout)} disabled={disabled || busy} onChange={event => { const file = event.target.files?.[0]; if (file) void choose(file); }} />;
  const preview = <>
    {/* Authenticated object URLs must preserve pixels in Next and static runtimes. */}
    {/* eslint-disable-next-line @next/next/no-img-element */}
    {url ? <img src={url} alt={uiText("선택한 첨부 이미지 미리보기")} className={styles.preview} /> : null}
    {value ? <Button type="button" variant="ghost" disabled={disabled || busy} onClick={() => { void discardDraft(value.id).catch(() => undefined); onChange(null); setError(null); }}>{uiText("사진 제거")}</Button> : null}
  </>;
  const feedback = <>
    {busy ? <p role="status">{uiText("사진을 업로드하고 확인하는 중…")}</p> : null}
    {error ? <InlineError>{error}{requireRecognition ? <a href="/settings">{uiText("이미지 인식 설정 열기")}</a> : null}</InlineError> : null}
  </>;
  if (renderLayout) return renderLayout({
    trigger: <>
      {fileInput}
      <IconButton className={styles.photoTrigger} type="button" variant="secondary" label={uiText("사진 첨부")}
        title={busy ? uiText("사진을 업로드하고 확인하는 중…") : uiText("사진 첨부")}
        disabled={disabled || busy} loading={busy} loadingLabel={uiText("사진을 업로드하고 확인하는 중…")}
        onClick={() => input.current?.click()}>
        <ImageIcon size={22} aria-hidden="true" />
      </IconButton>
    </>,
    preview, feedback,
  });
  return <div className={styles.picker}>
    <label className={styles.fileLabel}>{uiText("이미지 1장 첨부")}{fileInput}</label>
    {busy ? <p role="status">{uiText("사진을 업로드하고 확인하는 중…")}</p> : null}
    {preview}
    {error ? <InlineError>{error}{requireRecognition ? <a href="/settings">{uiText("이미지 인식 설정 열기")}</a> : null}</InlineError> : null}
  </div>;
}
