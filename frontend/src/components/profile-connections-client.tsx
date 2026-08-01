"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { ProfileListRow } from "@/components/profile-list-row";
import {
  getCharacterProfileConnections,
  getUserProfileConnections,
  type ProfileConnectionTab,
  type ProfileListPage,
  type ProfileRead,
} from "@/lib/community";
import { formatHandle } from "@/lib/profile";

type ProfileKind = "user" | "character";

const CONNECTION_TABS: Array<{
  key: ProfileConnectionTab;
  label: string;
  emptyText: string;
}> = [
  { key: "following", label: "팔로잉", emptyText: "아직 팔로잉한 프로필이 없습니다." },
  {
    key: "character_followers",
    label: "앵무 팔로워",
    emptyText: "아직 앵무 팔로워가 없습니다.",
  },
  {
    key: "user_followers",
    label: "사람 팔로워",
    emptyText: "아직 사람 팔로워가 없습니다.",
  },
];

export function ProfileConnectionsClient({
  profileKind,
  profileId,
  initialProfile,
  initialPage,
  activeTab,
  initialError,
}: {
  profileKind: ProfileKind;
  profileId: string;
  initialProfile: ProfileRead | null;
  initialPage: ProfileListPage | null;
  activeTab: ProfileConnectionTab;
  initialError: string | null;
}) {
  const { status: authStatus } = useAuth();
  const [page, setPage] = useState<ProfileListPage>(
    initialPage ?? { items: [], next_cursor: null },
  );
  const [loadingMore, setLoadingMore] = useState(false);
  const activeConfig =
    CONNECTION_TABS.find((tab) => tab.key === activeTab) ?? CONNECTION_TABS[0];
  const title = initialProfile?.profile.display_name ?? "프로필";
  const subtitle =
    profileKind === "character" && initialProfile?.profile.handle
      ? formatHandle(initialProfile.profile.handle)
      : null;
  const backHref =
    profileKind === "character"
      ? `/profiles/characters/${profileId}`
      : `/profiles/users/${profileId}`;

  useEffect(() => {
    if (authStatus !== "authenticated") return;
    let cancelled = false;

    const request =
      profileKind === "character"
        ? getCharacterProfileConnections(profileId, activeTab, { limit: 10 })
        : getUserProfileConnections(profileId, activeTab, { limit: 10 });

    request
      .then((next) => {
        if (!cancelled) setPage(next);
      })
      .catch(() => {
        // Keep the server-rendered public list if viewer-specific state cannot load.
      });

    return () => {
      cancelled = true;
    };
  }, [activeTab, authStatus, profileId, profileKind]);

  const loadMore = useCallback(async () => {
    if (!page.next_cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const next =
        profileKind === "character"
          ? await getCharacterProfileConnections(profileId, activeTab, {
              limit: 10,
              cursor: page.next_cursor,
            })
          : await getUserProfileConnections(profileId, activeTab, {
              limit: 10,
              cursor: page.next_cursor,
            });
      setPage((previous) => ({
        items: [...previous.items, ...next.items],
        next_cursor: next.next_cursor,
      }));
    } finally {
      setLoadingMore(false);
    }
  }, [activeTab, loadingMore, page.next_cursor, profileId, profileKind]);

  useEffect(() => {
    if (!page.next_cursor || loadingMore) return;

    function handleScroll() {
      const element = document.documentElement;
      const nearBottom = window.innerHeight + window.scrollY >= element.scrollHeight - 420;
      if (!nearBottom) return;
      void loadMore();
    }

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [loadMore, loadingMore, page.next_cursor]);

  return (
    <section className="min-h-screen bg-white">
      <div className="sticky top-0 z-10 border-b border-[#eaedf2] bg-white/95 backdrop-blur-sm">
        <div className="flex min-h-[72px] items-center gap-3 px-5 py-3 md:min-h-[82px] md:px-6">
          <Link
            href={backHref}
            className="inline-flex size-10 shrink-0 items-center justify-center rounded-full text-[#101828] transition-colors hover:bg-[#f6f7f9]"
            title="뒤로"
          >
            <ArrowLeft size={24} strokeWidth={2.4} />
          </Link>
          <div className="min-w-0">
            <h1 className="truncate text-[24px] font-extrabold text-[#101828]">
              {title}
            </h1>
            {subtitle ? (
              <p className="truncate text-[14px] font-bold text-[#667085]">
                {subtitle}
              </p>
            ) : null}
          </div>
        </div>

        <nav className="grid grid-cols-3" aria-label="팔로우 목록">
          {CONNECTION_TABS.map((tab) => {
            const selected = tab.key === activeTab;
            return (
              <Link
                key={tab.key}
                href={`${backHref}/follows?tab=${tab.key}`}
                className={`relative flex h-14 items-center justify-center text-[15px] font-extrabold transition-colors sm:text-[16px] ${
                  selected ? "text-[#101828]" : "text-[#667085] hover:bg-[#f9fafb] hover:text-[#101828]"
                }`}
                aria-current={selected ? "page" : undefined}
              >
                {tab.label}
                {selected ? (
                  <span className="absolute inset-x-0 bottom-0 h-1 bg-[#ff6b6b]" />
                ) : null}
              </Link>
            );
          })}
        </nav>
      </div>

      {initialError ? (
        <div className="mx-5 mt-6 rounded-[24px] border border-[#ffd7d7] bg-[#fff5f5] px-5 py-4 text-[15px] font-medium text-[#c24141] md:mx-9">
          {initialError}
        </div>
      ) : null}

      {page.items.length === 0 ? (
        <div className="p-8 text-center text-[15px] font-bold text-[#667085]">
          {activeConfig.emptyText}
        </div>
      ) : null}

      <div className="flex flex-col">
        {page.items.map((item) => (
          <ProfileListRow
            key={`${item.profile.profile_type}:${item.profile.id}:${item.viewer_following ? "following" : "not-following"}`}
            item={item}
            showFollowButton={activeTab !== "user_followers"}
          />
        ))}
      </div>
    </section>
  );
}
