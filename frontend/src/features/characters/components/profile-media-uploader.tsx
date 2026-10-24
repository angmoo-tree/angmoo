"use client";
import { useUiText } from "@/hooks/use-ui-text";
import { useUiErrorText } from "@/hooks/use-ui-error-text";


import { ImageIcon, Loader2, Upload } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import type { ChangeEvent } from "react";

import { Button } from "@/components/ui/button";
import { ImageCropDialog } from "@/components/media/image-crop-dialog";
import { cropToBlob, blobToBase64, type CropState } from "@/utils/image-crop";
import { useProductLeaveGuard } from "@/hooks/use-product-leave-guard";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { ProfileAvatar } from "@/components/ui/profile-avatar";
import type { AgentProfileMediaUploadInput } from "@/features/characters/types/agents";
import { usePrivateMediaResource } from "@/hooks/use-private-media-url";
import { useRuntimeMediaUrl } from "@/hooks/use-runtime-media-url";
import { useAuthRuntimeIdentity } from "@/hooks/use-auth-runtime-identity";
import { FileInputError } from "@/lib/media/read-file-input";
import { prepareProfileMedia, ProfileMediaInputError } from "../controllers/prepare-profile-media";

type MediaKind = "avatar" | "banner";

const SPECS: Record<MediaKind, { width: number; height: number; label: string }> = {
  avatar: { width: 768, height: 768, label: "아바타" },
  banner: { width: 1024, height: 384, label: "배너" },
};

type ProfileMediaUploaderProps = {
  scopeKey?: string;
  name: string;
  avatarUrl: string;
  bannerUrl: string;
  disabled: boolean;
  generationOverlay?: { kind: MediaKind; label: string } | null;
  onUpload: (data: AgentProfileMediaUploadInput) => Promise<void>;
};

export function ProfileMediaUploader(props: ProfileMediaUploaderProps) {
  const identity = useAuthRuntimeIdentity(props.scopeKey ?? "profile-media");
  return <ScopedProfileMediaUploader key={identity} {...props} />;
}

function ScopedProfileMediaUploader({
  name,
  avatarUrl,
  bannerUrl,
  disabled,
  generationOverlay,
  onUpload,
}: ProfileMediaUploaderProps) {
  const uiText = useUiText("characters"), errorText = useUiErrorText("characters");
  const avatarInputId = useId();
  const bannerInputId = useId();
  const mounted = useRef(true), operationRef = useRef(0);
  const draftBitmapRef = useRef<ImageBitmap | null>(null);
  const preparation = useRef<AbortController | null>(null);
  const [draft, setDraft] = useState<{
    kind: MediaKind;
    bitmap: ImageBitmap;
    naturalSize: { width: number; height: number };
  } | null>(null);
  const [crop, setCrop] = useState<CropState>({ scale: 1, offsetX: 0, offsetY: 0 });
  const [uploading, setUploading] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [mediaRevision, setMediaRevision] = useState({ avatar: 0, banner: 0 });
  const [error, setError] = useState<string | null>(null);
  const avatar = usePrivateMediaResource(avatarUrl, mediaRevision.avatar);
  const banner = usePrivateMediaResource(bannerUrl, mediaRevision.banner);
  const resolvedAvatarUrl = avatar.url;
  const resolvedBannerUrl = useRuntimeMediaUrl(banner.url);

  useProductLeaveGuard(Boolean(draft) || uploading || preparing);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false; operationRef.current += 1;
      preparation.current?.abort();
      draftBitmapRef.current?.close();
      draftBitmapRef.current = null;
    };
  }, []);

  const spec = draft ? SPECS[draft.kind] : SPECS.avatar;

  async function handleFileChange(kind: MediaKind, event: ChangeEvent<HTMLInputElement>) {
    const nextFile = event.target.files?.[0] ?? null;
    event.target.value = "";
    if (!nextFile) return;
    preparation.current?.abort();
    const controller = new AbortController(); preparation.current = controller;
    setError(null); setPreparing(true);
    const operation = ++operationRef.current, requestScope = captureAuthRequestScope();
    let bitmap: ImageBitmap | null = null;
    try {
      bitmap = await prepareProfileMedia(nextFile, controller.signal);
      if (!mounted.current || operationRef.current !== operation || !isCurrentAuthRequestScope(requestScope)) { bitmap.close(); return; }
      closeCropper(false);
      draftBitmapRef.current = bitmap;
      setDraft({
        kind,
        bitmap,
        naturalSize: { width: bitmap.width, height: bitmap.height },
      });
      setCrop({ scale: 1, offsetX: 0, offsetY: 0 });
    } catch (reason) {
      bitmap?.close();
      if (mounted.current && operationRef.current === operation && isCurrentAuthRequestScope(requestScope) && !controller.signal.aborted) {
        setError(uiText(reason instanceof FileInputError ? reason.code === "size" ? "이미지는 5MB 이하로 선택해주세요." : reason.code === "timeout" ? "사진 준비 시간이 초과됐어요. 다시 선택해 주세요." : "사진을 읽지 못했어요. 사진 목록에서 다시 선택해 주세요." : reason instanceof ProfileMediaInputError && reason.code === "format" ? "jpg, png, webp 이미지만 사용할 수 있습니다." : "사진 내용을 해석하지 못했어요. 다른 사진을 선택해 주세요."));
      }
    } finally {
      if (mounted.current && operationRef.current === operation) { setPreparing(false); preparation.current = null; }
    }
  }

  function closeCropper(advance = true) {
    if (advance) {
      preparation.current?.abort(); preparation.current = null;
      operationRef.current += 1; setPreparing(false);
    }
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
      if (current()) {
        const kind = draft.kind;
        setMediaRevision(previous => ({ ...previous, [kind]: previous[kind] + 1 }));
        closeCropper(false);
      }
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
            disabled={disabled || uploading}
            onChange={(event) => handleFileChange("banner", event)}
            className="absolute right-4 top-4 bg-surface-base shadow-[var(--shadow-summary)]"
          />
          {generationOverlay?.kind === "banner" ? (
            <MediaGenerationOverlay label={generationOverlay.label} />
          ) : null}
        </div>
        <div className="relative px-6 pb-6 pt-[70px]">
          <div className="absolute left-6 top-[-54px] flex rounded-full border-[5px] border-surface-base bg-surface-base shadow-[var(--shadow-summary)]">
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
              disabled={disabled || uploading}
              onChange={(event) => handleFileChange("avatar", event)}
            />
          </div>
        </div>
      </div>

      {error && !draft ? <p role="alert" className="mt-3 text-sm font-bold text-text-danger">{error}</p> : null}

      {preparing ? <div role="status"><p>{uiText("첨부할 사진을 준비하는 중…")}</p><Button type="button" variant="ghost" onClick={() => preparation.current?.abort()}>{uiText("사진 준비 취소")}</Button></div> : null}
      {([ ["avatar", avatar], ["banner", banner] ] as const).map(([kind, resource]) => <div key={kind}>
        {mediaRevision[kind] > 0 && resource.loading ? <p role="status">{uiText("저장한 이미지 미리보기를 불러오는 중…")}</p> : null}
        {resource.error ? <div role="alert"><p>{uiText(mediaRevision[kind] > 0 ? "이미지는 저장했지만 미리보기를 불러오지 못했어요." : "이미지 미리보기를 불러오지 못했어요.")}</p><Button type="button" variant="secondary" onClick={resource.retry}>{uiText("{{value0}} 미리보기 다시 불러오기", { value0: uiText(SPECS[kind].label) })}</Button></div> : null}
      </div>)}

      {draft ? (
        <ImageCropDialog bitmap={draft.bitmap} spec={spec} crop={crop} onCrop={setCrop} onApply={() => void handleUpload()} onCancel={() => closeCropper()}
          busy={uploading} disabled={disabled || uploading} error={error} labels={{ title: `${uiText(SPECS[draft.kind].label)} ${uiText("자르기")}`, close: uiText("닫기"), zoom: uiText("확대"), horizontal: uiText("가로"), vertical: uiText("세로"), apply: uiText("저장"), cancel: uiText("취소"), applying: uiText("이미지를 적용하는 중…") }} />
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
