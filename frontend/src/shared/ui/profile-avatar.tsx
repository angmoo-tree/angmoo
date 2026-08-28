"use client";

import { useState } from "react";

import { safeSameOriginMediaUrl, useRuntimeMediaUrl } from "@/shared/media/public";
import { getProfileColor, getProfileInitial } from "./profile-presentation";

export function ProfileAvatar({
  name,
  avatarUrl,
  sizeClassName = "size-[66px]",
  textClassName = "text-[28px]",
  className = "",
  allowBlob = false,
}: {
  name: string;
  avatarUrl?: string | null;
  sizeClassName?: string;
  textClassName?: string;
  className?: string;
  allowBlob?: boolean;
}) {
  const [imageFailed, setImageFailed] = useState(false);
  const safeAvatarUrl = safeSameOriginMediaUrl(avatarUrl, { allowBlob });
  const resolvedAvatarUrl = useRuntimeMediaUrl(safeAvatarUrl);

  if (resolvedAvatarUrl && !imageFailed) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={resolvedAvatarUrl}
        alt={`${name} 프로필 이미지`}
        onError={() => setImageFailed(true)}
        className={`${sizeClassName} shrink-0 rounded-full bg-[#f3f4f6] object-cover text-transparent ${className}`}
      />
    );
  }

  return (
    <div
      className={`${sizeClassName} ${getProfileColor(name)} flex shrink-0 items-center justify-center rounded-full font-extrabold ${textClassName} ${className}`}
      aria-label={`${name} 프로필`}
    >
      {getProfileInitial(name)}
    </div>
  );
}
