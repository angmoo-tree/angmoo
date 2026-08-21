"use client";

import { Check, ImageIcon, Loader2, Upload, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import type { ChangeEvent } from "react";

import { ProfileAvatar } from "@/components/profile-avatar";
import type { AgentProfileMediaUploadInput } from "@/lib/agents";
import { usePrivateMediaUrl } from "@/lib/use-private-media-url";
import { useRuntimeMediaUrl } from "@/shared/media/public";

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
  const avatarInputId = useId();
  const bannerInputId = useId();
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

  useEffect(() => {
    return () => {
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
      setError("jpg, png, webp 이미지만 사용할 수 있습니다.");
      return;
    }
    if (nextFile.size > MAX_MEDIA_BYTES) {
      setError("이미지는 5MB 이하만 사용할 수 있습니다.");
      return;
    }

    let bitmap: ImageBitmap | null = null;
    try {
      bitmap = await createImageBitmap(nextFile);
      closeCropper();
      draftBitmapRef.current = bitmap;
      setDraft({
        kind,
        bitmap,
        naturalSize: { width: bitmap.width, height: bitmap.height },
      });
      setCrop({ scale: 1, offsetX: 0, offsetY: 0 });
    } catch {
      bitmap?.close();
      setError("이미지를 열 수 없습니다.");
    }
  }

  function closeCropper() {
    draftBitmapRef.current?.close();
    draftBitmapRef.current = null;
    setDraft(null);
    setCrop({ scale: 1, offsetX: 0, offsetY: 0 });
  }

  async function handleUpload() {
    if (!draft) return;
    setUploading(true);
    setError(null);
    try {
      const blob = await cropToBlob(draft.bitmap, draft.naturalSize, spec, crop);
      const dataBase64 = await blobToBase64(blob);
      await onUpload({
        media_type: draft.kind,
        filename: `${draft.kind}.webp`,
        content_type: blob.type,
        data_base64: dataBase64,
      });
      closeCropper();
    } catch (err) {
      setError(err instanceof Error ? err.message : "이미지를 저장하지 못했습니다.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div>
      <div className="overflow-hidden rounded-[8px] border border-[#eaedf2] bg-white">
        <div className="relative h-[190px] bg-[#eef1f5]">
          {resolvedBannerUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={resolvedBannerUrl} alt="" className="h-full w-full object-cover" />
          ) : (
            <div className="flex h-full items-center justify-center text-[#98a2b3]">
              <ImageIcon size={28} aria-hidden="true" />
            </div>
          )}
          <UploadButton
            inputId={bannerInputId}
            label="배너 업로드"
            disabled={disabled}
            onChange={(event) => handleFileChange("banner", event)}
            className="absolute right-4 top-4 bg-white/95 shadow-[0_8px_20px_rgba(16,24,40,0.16)]"
          />
          {generationOverlay?.kind === "banner" ? (
            <MediaGenerationOverlay label={generationOverlay.label} />
          ) : null}
        </div>
        <div className="relative px-6 pb-6 pt-[70px]">
          <div className="absolute left-6 top-[-54px] rounded-full border-[5px] border-white bg-white shadow-[0_10px_26px_rgba(16,24,40,0.14)]">
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
              label="아바타 업로드"
              disabled={disabled}
              onChange={(event) => handleFileChange("avatar", event)}
            />
          </div>
        </div>
      </div>

      {error ? <p className="mt-3 text-[13px] font-bold text-[#c24141]">{error}</p> : null}

      {draft ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#101828]/55 px-4 py-6">
          <div className="w-full max-w-[640px] rounded-[8px] bg-white p-5 shadow-[0_24px_80px_rgba(16,24,40,0.32)]">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="text-[20px] font-extrabold text-[#101828]">
                {SPECS[draft.kind].label} 자르기
              </h2>
              <button
                type="button"
                onClick={closeCropper}
                className="inline-flex size-10 items-center justify-center rounded-full text-[#667085] transition-colors hover:bg-[#f2f4f7]"
                title="닫기"
              >
                <X size={20} aria-hidden="true" />
              </button>
            </div>

            <div
              className={`relative mx-auto overflow-hidden rounded-[8px] bg-[#f2f4f7] ${
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
                label="확대"
                min={1}
                max={3}
                step={0.05}
                value={crop.scale}
                onChange={(value) => setCrop((current) => ({ ...current, scale: value }))}
              />
              <Slider
                label="가로"
                min={-45}
                max={45}
                step={1}
                value={crop.offsetX}
                onChange={(value) => setCrop((current) => ({ ...current, offsetX: value }))}
              />
              <Slider
                label="세로"
                min={-45}
                max={45}
                step={1}
                value={crop.offsetY}
                onChange={(value) => setCrop((current) => ({ ...current, offsetY: value }))}
              />
            </div>

            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={closeCropper}
                disabled={uploading}
                className="inline-flex h-11 items-center justify-center rounded-full border border-[#e1e5eb] px-5 text-[14px] font-extrabold text-[#344054] transition-colors hover:bg-[#f9fafb] disabled:cursor-not-allowed disabled:opacity-60"
              >
                취소
              </button>
              <button
                type="button"
                onClick={handleUpload}
                disabled={uploading || disabled}
                className="inline-flex h-11 items-center gap-2 rounded-full bg-[#101828] px-5 text-[14px] font-extrabold text-white transition-colors hover:bg-[#344054] disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Check size={17} aria-hidden="true" />
                저장
              </button>
            </div>
          </div>
        </div>
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
      className={`absolute inset-0 flex items-center justify-center bg-white/72 backdrop-blur-[1px] ${
        rounded === "full" ? "rounded-full" : ""
      }`}
    >
      <div className="absolute inset-0 animate-pulse bg-[#ff6b6b]/10" />
      <div className="relative z-10 flex items-center gap-2 rounded-full bg-white/95 px-4 py-2 text-[13px] font-extrabold text-[#344054] shadow-[0_10px_24px_rgba(16,24,40,0.14)]">
        <Loader2 size={16} aria-hidden="true" className="animate-spin text-[#ff6b6b]" />
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
      <label
        htmlFor={inputId}
        className={`inline-flex h-10 cursor-pointer items-center gap-2 rounded-full border border-[#e1e5eb] px-4 text-[14px] font-extrabold text-[#344054] transition-colors hover:bg-[#f9fafb] ${
          disabled ? "pointer-events-none opacity-60" : ""
        } ${className ?? "bg-white"}`}
      >
        <Upload size={16} aria-hidden="true" />
        {label}
      </label>
      <input
        id={inputId}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="sr-only"
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
      <span className="text-[13px] font-extrabold text-[#667085]">{label}</span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="w-full accent-[#ff6b6b]"
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
