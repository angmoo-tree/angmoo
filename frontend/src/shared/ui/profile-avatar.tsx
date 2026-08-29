"use client";

import { safeSameOriginMediaUrl, useRuntimeMediaUrl } from "@/shared/media/public";
import { Avatar } from "./avatar";
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
  const safeAvatarUrl = safeSameOriginMediaUrl(avatarUrl, { allowBlob });
  const resolvedAvatarUrl = useRuntimeMediaUrl(safeAvatarUrl);

  return (
    <Avatar
      src={resolvedAvatarUrl}
      alt={`${name} 프로필 이미지`}
      fallback={getProfileInitial(name)}
      className={`${sizeClassName} shrink-0 ${className}`}
      fallbackClassName={`${getProfileColor(name)} font-extrabold ${textClassName}`}
    />
  );
}
