"use client";

import { Check, RefreshCw, X } from "lucide-react";

import type { GeneratedMediaCandidate } from "@/lib/generated-media";

export function GeneratedMediaPreviewCard({
  candidate,
  busy,
  applying,
  applyLabel,
  onApply,
  onRetry,
  onCancel,
}: {
  candidate: GeneratedMediaCandidate | null;
  busy: boolean;
  applying: boolean;
  applyLabel: string;
  onApply: () => void;
  onRetry: () => void;
  onCancel: () => void;
}) {
  if (!candidate) return null;
  const label = candidate.mediaType === "avatar" ? "아바타" : "배너";

  return (
    <div className="rounded-[8px] border border-[#eaedf2] bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[14px] font-extrabold text-[#101828]">
            생성된 {label} 이미지
          </p>
          <p className="mt-1 text-[13px] font-bold leading-5 text-[#667085]">
            마음에 들면 적용하고, 아니면 다시 생성할 수 있어요.
          </p>
        </div>
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className="inline-flex size-9 shrink-0 items-center justify-center rounded-full text-[#667085] transition-colors hover:bg-[#f2f4f7] disabled:cursor-not-allowed disabled:opacity-60"
          title="취소"
        >
          <X size={18} aria-hidden="true" />
        </button>
      </div>

      <div
        className={`mt-4 overflow-hidden rounded-[8px] bg-[#f2f4f7] ${
          candidate.mediaType === "avatar"
            ? "aspect-square w-full max-w-[220px]"
            : "aspect-[3/1] w-full"
        }`}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={candidate.objectUrl} alt="" className="h-full w-full object-cover" />
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onApply}
          disabled={busy}
          className="inline-flex h-10 items-center gap-2 rounded-full bg-[#101828] px-4 text-[14px] font-extrabold text-white transition-colors hover:bg-[#344054] disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Check size={16} aria-hidden="true" />
          {applying ? "적용 중..." : applyLabel}
        </button>
        <button
          type="button"
          onClick={onRetry}
          disabled={busy}
          className="inline-flex h-10 items-center gap-2 rounded-full border border-[#e1e5eb] bg-white px-4 text-[14px] font-extrabold text-[#344054] transition-colors hover:bg-[#f9fafb] disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw size={16} aria-hidden="true" />
          다시 생성
        </button>
      </div>
    </div>
  );
}
