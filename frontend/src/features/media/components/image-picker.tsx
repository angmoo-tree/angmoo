"use client";
import { useUiText } from "@/hooks/use-ui-text";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Image as ImageIcon } from "lucide-react";
import { Button, IconButton } from "@/components/ui/button";
import { InlineError } from "@/components/ui/feedback";
import { useRuntimeMediaUrl } from "@/hooks/use-runtime-media-url";
import { discardDraft, preflightImage, uploadImage } from "../api/media-client";
import styles from "./media-settings.module.css";
import { useAuthRuntimeIdentity } from "@/hooks/use-auth-runtime-identity";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { PhotoPreparationError } from "../utils/photo-header";
import { prepareUserPhoto } from "../utils/prepare-user-photo";

type Selection = { id: string; url: string; allowed: boolean };
type Props = {
  scopeKind: "character" | "thread" | "world" | "world_character"; scopeId: string; value: Selection | null;
  onChange: (value: Selection | null) => void; disabled?: boolean; requireRecognition?: boolean; onBusyChange?: (value: boolean) => void;
  renderLayout?: (slots: { trigger: ReactNode; preview: ReactNode; feedback: ReactNode }) => ReactNode;
  preparationPolicy?: "default" | "user-photo";
};
export function ImagePicker(props: Props) {
  const identity = useAuthRuntimeIdentity(`${props.scopeKind}:${props.scopeId}`);
  return <ScopedImagePicker key={identity} {...props} />;
}
const PHOTO_ERRORS = {
  photo_original_large: "원본 사진은 20MB 이하로 선택해주세요.",
  photo_unsupported: "JPG, PNG, WebP 또는 HEIF·HEIC 사진을 선택해주세요.",
  photo_damaged: "사진을 읽지 못했어요. 손상되지 않은 사진을 다시 선택해주세요.",
  photo_animated: "움직이는 이미지나 동영상은 첨부할 수 없어요. 사진 한 장을 선택해주세요.",
  photo_dimensions: "사진 해상도가 너무 커요. 16,384px 이하, 전체 64메가픽셀 이하로 선택해주세요.",
  photo_codec: "이 사진 형식을 변환하지 못했어요. JPG 또는 PNG로 다시 선택해주세요.",
  photo_timeout: "사진 준비 시간이 너무 길어 중단했어요. 더 작은 사진을 선택해주세요.",
  photo_preparation: "첨부할 사진을 준비하지 못했어요. 더 작은 사진을 선택해주세요.",
};
function ScopedImagePicker({ scopeKind, scopeId, value, onChange, disabled = false, requireRecognition = false, onBusyChange, renderLayout, preparationPolicy = "default" }: Props) {
  const uiText = useUiText("media");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preparing, setPreparing] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const selected = useRef(value);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { selected.current = value; }, [value]);
  useEffect(() => () => { controller.current?.abort(); controller.current = null; }, []);
  const url = useRuntimeMediaUrl(value?.url);
  async function choose(file: File) {
    controller.current?.abort();
    const operation = new AbortController(); controller.current = operation;
    const authScope = captureAuthRequestScope();
    const current = () => controller.current === operation && !operation.signal.aborted && isCurrentAuthRequestScope(authScope);
    setBusy(true); onBusyChange?.(true); setError(null);
    let assetId: string | null = null;
    try {
      setPreparing(preparationPolicy === "user-photo");
      const prepared = preparationPolicy === "user-photo" ? await prepareUserPhoto(file, operation.signal) : file;
      if (!current()) return;
      setPreparing(false);
      const asset = await uploadImage(prepared, scopeKind, scopeId, operation.signal); assetId = asset.id;
      const state = requireRecognition ? await preflightImage(asset.id, operation.signal) : { allowed: true, reason: null };
      if (!current()) { if (isCurrentAuthRequestScope(authScope)) await discardDraft(asset.id); return; }
      const old = selected.current;
      const next = { id: asset.id, url: asset.url, allowed: state.allowed };
      selected.current = next;
      onChange(next);
      if (old && old.id !== asset.id) void discardDraft(old.id).catch(() => undefined);
      if (!state.allowed) setError(uiText("이미지를 인식할 수 없어요. 이미지 인식 설정을 확인하거나 사진을 제거해주세요."));
    } catch (reason) {
      if (assetId && isCurrentAuthRequestScope(authScope)) void discardDraft(assetId).catch(() => undefined);
      if (current()) setError(reason instanceof PhotoPreparationError ? uiText(PHOTO_ERRORS[reason.code]) : uiText("사진을 첨부하지 못했어요. 입력한 내용과 이전 사진은 유지돼요."));
    } finally {
      if (controller.current === operation) { setBusy(false); setPreparing(false); onBusyChange?.(false); if (input.current) input.current.value = ""; }
    }
  }
  const fileInput = <input className={styles.fileInput} aria-label={uiText("첨부 이미지 선택")} ref={input} type="file" accept={preparationPolicy === "user-photo" ? "image/png,image/jpeg,image/webp,image/heif,image/heic,.heif,.heic" : "image/png,image/jpeg,image/webp"} hidden={Boolean(renderLayout)} disabled={disabled} onChange={event => { const file = event.target.files?.[0]; if (file) void choose(file); }} />;
  const preview = <>
    {/* Authenticated object URLs must preserve pixels in Next and static runtimes. */}
    {/* eslint-disable-next-line @next/next/no-img-element */}
    {url ? <img src={url} alt={uiText("선택한 첨부 이미지 미리보기")} className={styles.preview} /> : null}
    {value ? <Button type="button" variant="ghost" disabled={disabled} onClick={() => { controller.current?.abort(); selected.current = null; void discardDraft(value.id).catch(() => undefined); onChange(null); setError(null); }}>{uiText("사진 제거")}</Button> : null}
  </>;
  const feedback = <>
    {busy ? <><p role="status">{uiText(preparing ? "첨부할 사진을 준비하는 중…" : "사진을 업로드하고 확인하는 중…")}</p><Button type="button" variant="ghost" onClick={() => controller.current?.abort()}>{uiText("사진 준비 취소")}</Button></> : null}
    {error ? <InlineError>{error}{requireRecognition ? <a href="/settings">{uiText("이미지 인식 설정 열기")}</a> : null}</InlineError> : null}
  </>;
  if (renderLayout) return renderLayout({
    trigger: <>
      {fileInput}
      <IconButton className={styles.photoTrigger} type="button" variant="secondary" label={uiText("사진 첨부")}
        title={busy ? uiText("사진을 업로드하고 확인하는 중…") : uiText("사진 첨부")}
        disabled={disabled} aria-busy={busy}
        onClick={() => input.current?.click()}>
        <ImageIcon size={22} aria-hidden="true" />
      </IconButton>
    </>,
    preview, feedback,
  });
  return <div className={styles.picker}>
    <label className={styles.fileLabel}>{uiText("이미지 1장 첨부")}{fileInput}</label>
    {preview}
    {feedback}
  </div>;
}
