"use client";
import { useUiText } from "@/hooks/use-ui-text";
import { useUiErrorText } from "@/hooks/use-ui-error-text";


import { Check, ImageIcon, Loader2, Upload } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import type { ChangeEvent } from "react";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { useProductLeaveGuard } from "@/hooks/use-product-leave-guard";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { ProfileAvatar } from "@/components/ui/profile-avatar";
import type { AgentProfileMediaUploadInput } from "@/features/characters/types/agents";
import { usePrivateMediaUrl } from "@/hooks/use-private-media-url";
import { useRuntimeMediaUrl } from "@/hooks/use-runtime-media-url";

type MediaKind = "avatar" | "banner";

type CropState = {
  scale: number;
  offsetX: number;
  offsetY: number;
};

const SPECS: Record<MediaKind, { width: number; height: number; label: string }> = {
  avatar: { width: 768, height: 768, label: "아바타" },
  banner: { width: 1024, height: 384, label: "배너" },
};

const ACCEPTED_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const MAX_MEDIA_BYTES = 5 * 1024 * 1024;

export function ProfileMediaUploader({
  name,
  avatarUrl,
  bannerUrl,
  disabled,
  generationOverlay,
  onUpload,
}: {
  name: string;
  avatarUrl: string;
  bannerUrl: string;
  disabled: boolean;
  generationOverlay?: { kind: MediaKind; label: string } | null;
  onUpload: (data: AgentProfileMediaUploadInput) => Promise<void>;
}) {
  const uiText = useUiText("characters"), errorText = useUiErrorText("characters");
  const avatarInputId = useId();
  const bannerInputId = useId();
  const mounted = useRef(true), operationRef = useRef(0);
  const draftBitmapRef = useRef<ImageBitmap | null>(null);
  const [draft, setDraft] = useState<{
    kind: MediaKind;
    bitmap: ImageBitmap;
    naturalSize: { width: number; height: number };
  } | null>(null);
  const [crop, setCrop] = useState<CropState>({ scale: 1, offsetX: 0, offsetY: 0 });
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const resolvedAvatarUrl = usePrivateMediaUrl(avatarUrl);
  const privateBannerUrl = usePrivateMediaUrl(bannerUrl);
  const resolvedBannerUrl = useRuntimeMediaUrl(privateBannerUrl);

  useProductLeaveGuard(Boolean(draft) || uploading);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false; operationRef.current += 1;
      draftBitmapRef.current?.close();
      draftBitmapRef.current = null;
    };
  }, []);

  const spec = draft ? SPECS[draft.kind] : SPECS.avatar;

  async function handleFileChange(kind: MediaKind, event: ChangeEvent<HTMLInputElement>) {
    const nextFile = event.target.files?.[0] ?? null;
    event.target.value = "";
    if (!nextFile) return;
    setError(null);
    if (!ACCEPTED_TYPES.has(nextFile.type)) {
      setError(uiText("jpg, png, webp 이미지만 사용할 수 있습니다."));
      return;
    }
    if (nextFile.size > MAX_MEDIA_BYTES) {
      setError(uiText("이미지는 5MB 이하만 사용할 수 있습니다."));
      return;
    }

    const operation = ++operationRef.current, requestScope = captureAuthRequestScope();
    let bitmap: ImageBitmap | null = null;
    try {
      bitmap = await createImageBitmap(nextFile);
      if (!mounted.current || operationRef.current !== operation || !isCurrentAuthRequestScope(requestScope)) { bitmap.close(); return; }
      closeCropper(false);
      draftBitmapRef.current = bitmap;
      setDraft({
        kind,
        bitmap,
        naturalSize: { width: bitmap.width, height: bitmap.height },
      });
      setCrop({ scale: 1, offsetX: 0, offsetY: 0 });
    } catch {
      bitmap?.close();
      if (mounted.current && operationRef.current === operation && isCurrentAuthRequestScope(requestScope)) setError(uiText("이미지를 열 수 없습니다."));
    }
  }

  function closeCropper(advance = true) {
    if (advance) operationRef.current += 1;
    draftBitmapRef.current?.close();
    draftBitmapRef.current = null;
    setDraft(null);
    setCrop({ scale: 1, offsetX: 0, offsetY: 0 });
  }

  async function handleUpload() {
    if (!draft || uploading) return;
    const operation = ++operationRef.current, requestScope = captureAuthRequestScope();
    const current = () => mounted.current && operationRef.current === operation && isCurrentAuthRequestScope(requestScope);
    setUploading(true);
    setError(null);
    try {
      const blob = await cropToBlob(draft.bitmap, draft.naturalSize, spec, crop);
      const dataBase64 = await blobToBase64(blob);
      if (!current()) return;
      await onUpload({
        media_type: draft.kind,
        filename: `${draft.kind}.webp`,
        content_type: blob.type,
        data_base64: dataBase64,
      });
      if (current()) closeCropper(false);
    } catch (err) {
      if (current()) setError(errorText(err, "이미지를 저장하지 못했습니다."));
    } finally {
      if (current()) setUploading(false);
    }
  }

  return (
    <div>
      <div className="overflow-hidden rounded-[var(--radius-control)] border border-border-default bg-surface-base">
        <div className="relative h-[190px] bg-surface-muted">
          {resolvedBannerUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={resolvedBannerUrl} alt="" className="h-full w-full object-cover" />
          ) : (
            <div className="flex h-full items-center justify-center text-text-muted">
              <ImageIcon size={28} aria-hidden="true" />
            </div>
          )}
          <UploadButton
            inputId={bannerInputId}
            label={uiText("배너 업로드")}
            disabled={disabled}
            onChange={(event) => handleFileChange("banner", event)}
            className="absolute right-4 top-4 bg-surface-base shadow-[var(--shadow-summary)]"
          />
          {generationOverlay?.kind === "banner" ? (
            <MediaGenerationOverlay label={generationOverlay.label} />
          ) : null}
        </div>
        <div className="relative px-6 pb-6 pt-[70px]">
          <div className="absolute left-6 top-[-54px] rounded-full border-[5px] border-surface-base bg-surface-base shadow-[var(--shadow-summary)]">
            <ProfileAvatar
              name={name}
              avatarUrl={resolvedAvatarUrl}
              allowBlob
              sizeClassName="size-[108px]"
              textClassName="text-[40px]"
            />
            {generationOverlay?.kind === "avatar" ? (
              <MediaGenerationOverlay label={generationOverlay.label} rounded="full" />
            ) : null}
          </div>
          <div className="pt-4">
            <UploadButton
              inputId={avatarInputId}
              label={uiText("아바타 업로드")}
              disabled={disabled}
              onChange={(event) => handleFileChange("avatar", event)}
            />
          </div>
        </div>
      </div>

      {error && !draft ? <p role="alert" className="mt-3 text-sm font-bold text-text-danger">{error}</p> : null}

      {draft ? (
        <Dialog open title={`${uiText(SPECS[draft.kind].label)} ${uiText("자르기")}`} closeLabel={uiText("닫기")} closeOnBackdrop={false} closeOnEscape={!uploading}
          closeButtonAttributes={{ disabled: uploading }} onOpenChange={open => { if (!open && !uploading) closeCropper(); }}>
            <div
              className={`relative mx-auto overflow-hidden rounded-[var(--radius-control)] bg-surface-muted ${
                draft.kind === "avatar" ? "aspect-square w-full max-w-[360px]" : "aspect-[3/1] w-full"
              }`}
            >
              <CropPreview
                bitmap={draft.bitmap}
                naturalSize={draft.naturalSize}
                spec={spec}
                crop={crop}
              />
            </div>

            <div className="mt-5 grid gap-4">
              <Slider
                label={uiText("확대")}
                min={1}
                max={3}
                step={0.05}
                value={crop.scale}
                onChange={(value) => setCrop((current) => ({ ...current, scale: value }))}
              />
              <Slider
                label={uiText("가로")}
                min={-45}
                max={45}
                step={1}
                value={crop.offsetX}
                onChange={(value) => setCrop((current) => ({ ...current, offsetX: value }))}
              />
              <Slider
                label={uiText("세로")}
                min={-45}
                max={45}
                step={1}
                value={crop.offsetY}
                onChange={(value) => setCrop((current) => ({ ...current, offsetY: value }))}
              />
            </div>

            {error ? <p role="alert" className="mt-3 text-text-danger">{error}</p> : null}
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <Button type="button" variant="secondary" onClick={() => closeCropper()} disabled={uploading}>{uiText("취소")}</Button>
              <Button type="button" onClick={() => void handleUpload()} loading={uploading} disabled={disabled}><Check size={17} aria-hidden="true" />{uiText("저장")}</Button>
            </div>
        </Dialog>
      ) : null}
    </div>
  );
}

function MediaGenerationOverlay({
  label,
  rounded = "normal",
}: {
  label: string;
  rounded?: "normal" | "full";
}) {
  return (
    <div
      className={`absolute inset-0 flex items-center justify-center bg-surface-base/70 backdrop-blur-[1px] ${
        rounded === "full" ? "rounded-full" : ""
      }`}
    >
      <div className="absolute inset-0 animate-pulse motion-reduce:animate-none bg-action-primary/10" />
      <div className="relative z-10 flex items-center gap-2 rounded-full bg-surface-base px-4 py-2 text-[13px] font-extrabold text-text-primary shadow-[var(--shadow-summary)]">
        <Loader2 size={16} aria-hidden="true" className="animate-spin motion-reduce:animate-none text-action-primary" />
        {label}
      </div>
    </div>
  );
}

function UploadButton({
  inputId,
  label,
  disabled,
  className,
  onChange,
}: {
  inputId: string;
  label: string;
  disabled: boolean;
  className?: string;
  onChange: (event: ChangeEvent<HTMLInputElement>) => void;
}) {
  return (
    <>
      <Button type="button" variant="secondary" disabled={disabled} className={className}
        onClick={() => (document.getElementById(inputId) as HTMLInputElement | null)?.click()}>
        <Upload size={16} aria-hidden="true" />{label}
      </Button>
      <input
        id={inputId}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        disabled={disabled}
        onChange={onChange}
      />
    </>
  );
}

function Slider({
  label,
  min,
  max,
  step,
  value,
  onChange,
}: {
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="grid gap-2">
      <span className="text-[13px] font-extrabold text-text-secondary">{label}</span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="min-h-11 w-full accent-action-primary"
      />
    </label>
  );
}

function CropPreview({
  bitmap,
  naturalSize,
  spec,
  crop,
}: {
  bitmap: ImageBitmap;
  naturalSize: { width: number; height: number };
  spec: { width: number; height: number };
  crop: CropState;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.width = spec.width;
    canvas.height = spec.height;
    const context = canvas.getContext("2d");
    if (!context) return;
    drawCroppedImage(context, bitmap, naturalSize, spec, crop);
  }, [bitmap, crop, naturalSize, spec]);

  return <canvas ref={canvasRef} aria-hidden="true" className="h-full w-full" />;
}

async function cropToBlob(
  bitmap: ImageBitmap,
  naturalSize: { width: number; height: number },
  spec: { width: number; height: number },
  crop: CropState,
) {
  const canvas = document.createElement("canvas");
  canvas.width = spec.width;
  canvas.height = spec.height;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("이미지를 처리하지 못했습니다.");

  drawCroppedImage(context, bitmap, naturalSize, spec, crop);

  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (blob) resolve(blob);
        else reject(new Error("이미지를 저장하지 못했습니다."));
      },
      "image/webp",
      0.8,
    );
  });
}

function drawCroppedImage(
  context: CanvasRenderingContext2D,
  bitmap: ImageBitmap,
  naturalSize: { width: number; height: number },
  spec: { width: number; height: number },
  crop: CropState,
) {
  context.clearRect(0, 0, spec.width, spec.height);
  const baseScale = Math.max(spec.width / naturalSize.width, spec.height / naturalSize.height);
  const drawWidth = naturalSize.width * baseScale * crop.scale;
  const drawHeight = naturalSize.height * baseScale * crop.scale;
  const centerX = spec.width * (0.5 + crop.offsetX / 100);
  const centerY = spec.height * (0.5 + crop.offsetY / 100);

  context.drawImage(
    bitmap,
    centerX - drawWidth / 2,
    centerY - drawHeight / 2,
    drawWidth,
    drawHeight,
  );
}

function blobToBase64(blob: Blob) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result ?? "");
      resolve(result.includes(",") ? result.split(",")[1] : result);
    };
    reader.onerror = () => reject(new Error("이미지를 읽지 못했습니다."));
    reader.readAsDataURL(blob);
  });
}
