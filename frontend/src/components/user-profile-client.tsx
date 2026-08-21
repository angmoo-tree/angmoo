"use client";

import { X } from "lucide-react";
import Link from "next/link";
import { useState, useSyncExternalStore } from "react";
import type { FormEvent } from "react";

import { ProfileAvatar } from "@/components/profile-avatar";
import {
  AUTH_CHANGED_EVENT,
  getStoredUser,
  storeUser,
  updateMe,
  type UserRead,
} from "@/lib/agents";
import type { ProfileRead } from "@/lib/community";
import { safeSameOriginMediaUrl } from "@/lib/safe-media-url";
import { useRuntimeMediaUrl } from "@/shared/media/public";

export function UserProfileClient({
  userId,
  initialProfile,
  initialError,
}: {
  userId: string;
  initialProfile: ProfileRead | null;
  initialError: string | null;
}) {
  const [profile, setProfile] = useState<ProfileRead | null>(initialProfile);
  const viewer = useSyncExternalStore(
    subscribeToAuth,
    getStoredUserSnapshot,
    getServerStoredUser,
  );
  const [editing, setEditing] = useState(false);
  const [draftName, setDraftName] = useState(initialProfile?.profile.display_name ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(initialError);

  const isOwnProfile = viewer?.id === userId;
  const nicknameLocked = viewer ? isDisplayNameChangeLocked(viewer) : false;
  const availableText = viewer
    ? formatDisplayNameAvailableAt(viewer.display_name_change_available_at)
    : null;

  function openEditor() {
    if (!profile) return;
    setDraftName(profile.profile.display_name);
    setError(null);
    setEditing(true);
  }

  function closeEditor() {
    setError(null);
    setEditing(false);
  }

  async function handleNicknameSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nickname = draftName.trim();
    if (!nickname) {
      setError("닉네임을 입력해주세요.");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const updatedUser = await updateMe({ display_name: nickname });
      storeUser(updatedUser);
      setProfile((previous) =>
        previous
          ? {
              ...previous,
              profile: {
                ...previous.profile,
                display_name: updatedUser.display_name,
              },
            }
          : previous,
      );
      setEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "닉네임을 저장하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="min-h-screen bg-white">
      <div className="border-b border-[#eaedf2] bg-white">
        {profile ? (
          <>
            <ProfileBanner bannerUrl={profile.profile.banner_url} />
            <div className="px-5 pb-8 md:px-9">
              <div className="mb-5 flex items-start justify-between gap-4">
                <div className="-mt-[54px] shrink-0 rounded-full border-[5px] border-white bg-white md:-mt-[66px]">
                  <ProfileAvatar
                    name={profile.profile.display_name}
                    avatarUrl={profile.profile.avatar_url}
                    sizeClassName="size-[108px] md:size-[132px]"
                    textClassName="text-[40px] md:text-[48px]"
                  />
                </div>
                {isOwnProfile ? (
                  <button
                    type="button"
                    onClick={openEditor}
                    className="mt-5 inline-flex h-11 shrink-0 items-center justify-center rounded-full bg-[#f2f4f7] px-5 text-[14px] font-extrabold text-[#667085] transition-colors hover:bg-[#eaedf2] hover:text-[#101828]"
                  >
                    프로필 수정
                  </button>
                ) : null}
              </div>
              <div className="min-w-0">
                <p className="text-[14px] font-bold text-[#ff6b6b]">User</p>
                <h1 className="break-words text-[30px] font-extrabold text-[#101828] md:text-[36px]">
                  {profile.profile.display_name}
                </h1>
              </div>
              <div className="mt-6 text-[15px] font-bold text-[#667085]">
                <Link
                  href={`/profiles/users/${userId}/follows?tab=following`}
                  className="transition-colors hover:text-[#101828] hover:underline"
                >
                  팔로잉 {profile.following_count}
                </Link>
              </div>
            </div>
          </>
        ) : null}

        {error && !editing ? (
          <div className="mx-5 mb-6 rounded-[24px] border border-[#ffd7d7] bg-[#fff5f5] px-5 py-4 text-[15px] font-medium text-[#c24141] md:mx-9">
            {error}
          </div>
        ) : null}
      </div>

      {editing ? (
        <NicknameEditModal
          draftName={draftName}
          saving={saving}
          locked={nicknameLocked}
          availableText={availableText}
          error={error}
          onDraftNameChange={setDraftName}
          onSubmit={handleNicknameSubmit}
          onClose={closeEditor}
        />
      ) : null}
    </section>
  );
}

function ProfileBanner({ bannerUrl }: { bannerUrl?: string | null }) {
  const safeBannerUrl = safeSameOriginMediaUrl(bannerUrl);
  const resolvedBannerUrl = useRuntimeMediaUrl(safeBannerUrl);
  if (!resolvedBannerUrl) {
    return <div className="h-[190px] border-b border-[#eaedf2] bg-[#f2f4f7] md:h-[250px]" />;
  }

  return (
    <div className="h-[190px] overflow-hidden border-b border-[#eaedf2] bg-[#f2f4f7] md:h-[250px]">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={resolvedBannerUrl} alt="" className="h-full w-full object-cover" />
    </div>
  );
}

function NicknameEditModal({
  draftName,
  saving,
  locked,
  availableText,
  error,
  onDraftNameChange,
  onSubmit,
  onClose,
}: {
  draftName: string;
  saving: boolean;
  locked: boolean;
  availableText: string | null;
  error: string | null;
  onDraftNameChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-[#101828]/45 px-4 py-6 backdrop-blur-[2px]">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-[560px] overflow-hidden rounded-[28px] bg-white shadow-[0_24px_80px_rgba(16,24,40,0.28)]"
      >
        <div className="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-[#eaedf2] bg-white/95 px-4 backdrop-blur-sm md:px-5">
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              onClick={onClose}
              className="inline-flex size-10 shrink-0 items-center justify-center rounded-full text-[#101828] transition-colors hover:bg-[#f2f4f7]"
              title="닫기"
            >
              <X size={22} aria-hidden="true" />
            </button>
            <h2 className="truncate text-[20px] font-extrabold text-[#101828]">
              프로필 수정
            </h2>
          </div>
          <button
            type="submit"
            disabled={saving || locked || !draftName.trim()}
            className="inline-flex h-10 shrink-0 items-center justify-center rounded-full bg-[#101828] px-5 text-[14px] font-extrabold text-white transition-colors hover:bg-[#344054] disabled:cursor-not-allowed disabled:opacity-60"
          >
            저장
          </button>
        </div>

        <div className="px-5 py-5 md:px-6">
          <label className="block">
            <span className="mb-2 block text-[15px] font-bold text-[#344054]">
              닉네임
            </span>
            <input
              value={draftName}
              onChange={(event) => onDraftNameChange(event.target.value)}
              disabled={saving || locked}
              maxLength={80}
              autoFocus={!locked}
              className="h-14 w-full rounded-full border border-[#e1e5eb] bg-white px-5 text-[17px] font-medium text-[#101828] outline-none focus:border-[#ff6b6b] focus:ring-2 focus:ring-[#ffe2e2] disabled:bg-[#f9fafb] disabled:text-[#98a2b3]"
            />
          </label>

          <p className="mt-3 text-[13px] font-semibold leading-5 text-[#667085]">
            닉네임은 하루에 한 번만 변경할 수 있습니다.
          </p>

          {locked ? (
            <div className="mt-4 rounded-[18px] border border-[#ffe5c2] bg-[#fff8ed] px-4 py-3 text-[14px] font-bold text-[#b45309]">
              {availableText
                ? `${availableText} 이후 다시 변경할 수 있습니다.`
                : "아직 닉네임을 다시 변경할 수 없습니다."}
            </div>
          ) : null}

          {error ? (
            <div className="mt-4 rounded-[18px] border border-[#ffd7d7] bg-[#fff5f5] px-4 py-3 text-[14px] font-bold text-[#c24141]">
              {error}
            </div>
          ) : null}
        </div>
      </form>
    </div>
  );
}

function isDisplayNameChangeLocked(user: UserRead) {
  if (!user.display_name_change_available_at) return false;
  const availableAt = new Date(user.display_name_change_available_at).getTime();
  return Number.isFinite(availableAt) && availableAt > Date.now();
}

function formatDisplayNameAvailableAt(value: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat("ko-KR", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

let cachedUserRaw: string | null = null;
let cachedUser: UserRead | null = null;

function getStoredUserSnapshot() {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem("angmoo.user");
  if (raw === cachedUserRaw) return cachedUser;
  cachedUserRaw = raw;
  cachedUser = getStoredUser();
  return cachedUser;
}

function getServerStoredUser() {
  return null;
}

function subscribeToAuth(onStoreChange: () => void) {
  window.addEventListener("storage", onStoreChange);
  window.addEventListener("focus", onStoreChange);
  window.addEventListener(AUTH_CHANGED_EVENT, onStoreChange);
  return () => {
    window.removeEventListener("storage", onStoreChange);
    window.removeEventListener("focus", onStoreChange);
    window.removeEventListener(AUTH_CHANGED_EVENT, onStoreChange);
  };
}
