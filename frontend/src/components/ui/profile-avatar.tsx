"use client";
import { useUiText } from "@/hooks/use-ui-text";


import { safeSameOriginMediaUrl } from "@/lib/media/safe-media-url";
import { useRuntimeMediaUrl } from "@/hooks/use-runtime-media-url";
import { Avatar } from "@/components/ui/avatar";
import { getProfileColor, getProfileInitial } from "@/utils/profile-presentation";

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
  const uiText = useUiText("shell");
  const safeAvatarUrl = safeSameOriginMediaUrl(avatarUrl, { allowBlob });
  const resolvedAvatarUrl = useRuntimeMediaUrl(safeAvatarUrl);

  return (
    <Avatar
      src={resolvedAvatarUrl}
      alt={uiText("{{value0}} 프로필 이미지", {value0: name})}
      fallback={getProfileInitial(name)}
      className={`${sizeClassName} shrink-0 ${className}`}
      fallbackClassName={`${getProfileColor(name)} font-extrabold ${textClassName}`}
    />
  );
}
