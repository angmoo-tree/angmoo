"use client";

import Link from "next/link";
import { useState } from "react";

import { ProfileAvatar } from "@/components/profile-avatar";
import { followProfile, type ProfileListItem } from "@/lib/community";
import { formatHandle } from "@/lib/profile";

type ProfileListRowProps = {
  item: ProfileListItem;
  showFollowButton?: boolean;
};

export function ProfileListRow({ item, showFollowButton = true }: ProfileListRowProps) {
  const profile = item.profile;
  const [optimisticFollowing, setOptimisticFollowing] = useState(false);
  const [saving, setSaving] = useState(false);
  const following = item.viewer_following || optimisticFollowing;
  const href =
    profile.profile_type === "character"
      ? `/profiles/characters/${profile.id}`
      : `/profiles/users/${profile.id}`;
  const canShowFollowButton = showFollowButton && profile.profile_type === "character";

  async function handleFollowClick() {
    if (following || saving || profile.profile_type !== "character") return;
    setSaving(true);
    try {
      await followProfile({
        target_type: "character",
        target_id: profile.id,
      });
      setOptimisticFollowing(true);
    } finally {
      setSaving(false);
    }
  }

  return (
    <article className="border-b border-[#eaedf2] bg-white px-5 py-6 transition-colors hover:bg-[#f9fafb] md:px-9">
      <div className="flex items-start gap-4">
        <Link href={href} className="shrink-0 rounded-full focus:outline-none focus:ring-2 focus:ring-[#ff6b6b]/30">
          <ProfileAvatar
            name={profile.display_name}
            avatarUrl={profile.avatar_url}
            sizeClassName="size-[56px]"
            textClassName="text-[24px]"
          />
        </Link>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center justify-between gap-3">
            <Link
              href={href}
              className="min-w-0 rounded-[12px] focus:outline-none focus:ring-2 focus:ring-[#ff6b6b]/30"
            >
              <div className="truncate text-[20px] font-extrabold text-[#101828]">
                {profile.display_name}
              </div>
              {profile.profile_type === "character" && profile.handle ? (
                <div className="text-[16px] font-bold text-[#667085]">
                  {formatHandle(profile.handle)}
                </div>
              ) : null}
            </Link>
            {canShowFollowButton ? (
              <button
                type="button"
                onClick={handleFollowClick}
                disabled={saving || following}
                className={`shrink-0 rounded-full px-5 py-2 text-[14px] font-extrabold text-white ${
                  following ? "bg-[#7a808b]" : "bg-[#101828] hover:bg-[#344054]"
                }`}
              >
                {following ? "팔로우 중" : saving ? "처리 중" : "팔로우"}
              </button>
            ) : null}
          </div>
          {item.one_liner ? (
            <Link
              href={href}
              className="mt-3 block rounded-[12px] focus:outline-none focus:ring-2 focus:ring-[#ff6b6b]/30"
            >
              <p className="line-clamp-3 break-words text-[16px] font-medium leading-7 text-[#475467]">
              {item.one_liner}
              </p>
            </Link>
          ) : null}
        </div>
      </div>
    </article>
  );
}
