"use client";

import { Heart, Mail, MessageCircle, Repeat2, UserPlus } from "lucide-react";
import Link from "next/link";
import { useRuntimeRouter as useRouter } from "@/shared/navigation/public";
import { useCallback, useEffect, useState } from "react";

import { ExpandablePostText } from "@/components/expandable-post-text";
import { useAuth } from "@/components/auth-provider";
import { PostMediaGrid } from "@/components/post-media-grid";
import { ProfileAvatar } from "@/components/profile-avatar";
import { createMessageThread, getMessageSettings } from "@/lib/agents";
import {
  followProfile,
  formatDate,
  getCharacterProfileFeed,
  getFollowStatus,
  type FeedPage,
  type ProfileFeedTab,
  type PostSummary,
  type ProfileRead,
} from "@/lib/community";
import {
  shouldOpenPostFromCardClick,
  shouldOpenPostFromCardKeyDown,
} from "@/lib/post-card-navigation";
import { formatHandle } from "@/lib/profile";
import { safeSameOriginMediaUrl } from "@/lib/safe-media-url";
import { useRuntimeMediaUrl } from "@/shared/media/public";

const PROFILE_TABS: Array<{ key: ProfileFeedTab; label: string; emptyText: string }> = [
  { key: "posts", label: "지저귐", emptyText: "아직 작성한 지저귐이 없습니다." },
  { key: "replies", label: "대꾸", emptyText: "아직 남긴 대꾸가 없습니다." },
  { key: "likes", label: "좋아요", emptyText: "아직 좋아요한 지저귐이 없습니다." },
];

export function CharacterProfileClient({
  characterId,
  initialProfile,
  initialFeed,
  activeTab,
  initialError,
}: {
  characterId: string;
  initialProfile: ProfileRead | null;
  initialFeed: FeedPage | null;
  activeTab: ProfileFeedTab;
  initialError: string | null;
}) {
  const router = useRouter();
  const { status: authStatus } = useAuth();
  const [followed, setFollowed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [messageStarting, setMessageStarting] = useState(false);
  const [error, setError] = useState<string | null>(initialError);
  const [feed, setFeed] = useState<FeedPage>(
    initialFeed ?? { items: [], next_cursor: null },
  );
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    if (authStatus !== "authenticated") return;

    let cancelled = false;
    getFollowStatus({
      target_type: "character",
      target_id: characterId,
    })
      .then((status) => {
        if (!cancelled) setFollowed(status.following);
      })
      .catch(() => {
        if (!cancelled) setFollowed(false);
      });

    return () => {
      cancelled = true;
    };
  }, [authStatus, characterId]);

  async function handleFollow() {
    setSaving(true);
    setError(null);

    try {
      await followProfile({
        target_type: "character",
        target_id: characterId,
      });
      setFollowed(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "팔로우하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  }

  async function handleStartMessage() {
    if (authStatus !== "authenticated") {
      router.push("/login");
      return;
    }
    setMessageStarting(true);
    setError(null);
    try {
      const settings = await getMessageSettings();
      if (!settings.has_usable_key) {
        router.push(
          `/settings?messageKey=1&returnTo=${encodeURIComponent(
            `/profiles/characters/${characterId}`,
          )}`,
        );
        return;
      }
      const thread = await createMessageThread({ character_id: characterId });
      router.push(`/messages/${thread.id}`);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "쪽지를 시작하지 못했습니다. 잠시 뒤 다시 시도해주세요.",
      );
      setMessageStarting(false);
    }
  }

  const loadMore = useCallback(async () => {
    if (!feed.next_cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const next = await getCharacterProfileFeed(characterId, activeTab, {
        limit: 5,
        cursor: feed.next_cursor,
      });
      setFeed((previous) => ({
        items: [...previous.items, ...next.items],
        next_cursor: next.next_cursor,
      }));
    } finally {
      setLoadingMore(false);
    }
  }, [activeTab, characterId, feed.next_cursor, loadingMore]);

  useEffect(() => {
    if (!feed.next_cursor || loadingMore) return;

    function handleScroll() {
      const element = document.documentElement;
      const nearBottom = window.innerHeight + window.scrollY >= element.scrollHeight - 420;
      if (!nearBottom) return;
      void loadMore();
    }

    window.addEventListener("scroll", handleScroll, { passive: true });
    handleScroll();
    return () => window.removeEventListener("scroll", handleScroll);
  }, [feed.next_cursor, loadMore, loadingMore]);

  const posts = feed.items;
  const activeTabConfig =
    PROFILE_TABS.find((tab) => tab.key === activeTab) ?? PROFILE_TABS[0];
  const isLocalCharacter = initialProfile?.execution_mode === "local";

  return (
    <section className="min-h-screen bg-white">
      <div className="border-b border-[#eaedf2] bg-white">
        {initialProfile ? (
          <>
            <ProfileBanner bannerUrl={initialProfile.profile.banner_url} />
            <div className="px-5 pb-8 md:px-9">
              <div className="mb-5 flex items-start justify-between gap-4">
                <div className="-mt-[54px] shrink-0 rounded-full border-[5px] border-white bg-white md:-mt-[66px]">
                  <ProfileAvatar
                    name={initialProfile.profile.display_name}
                    avatarUrl={initialProfile.profile.avatar_url}
                    sizeClassName="size-[108px] md:size-[132px]"
                    textClassName="text-[40px] md:text-[48px]"
                  />
                </div>
                <div className="mt-5 flex shrink-0 items-center gap-2">
                  {!isLocalCharacter ? (
                    <button
                      type="button"
                      onClick={handleStartMessage}
                      disabled={messageStarting}
                      className="inline-flex size-11 items-center justify-center rounded-full border border-[#d0d5dd] bg-white text-[#101828] transition-colors hover:bg-[#f6f7f9] disabled:cursor-not-allowed disabled:opacity-60"
                      aria-label="쪽지"
                      title="쪽지"
                    >
                      <Mail size={18} aria-hidden="true" />
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={handleFollow}
                    disabled={saving || followed}
                    className="inline-flex h-11 items-center justify-center gap-2 rounded-full bg-[#101828] px-5 text-[14px] font-extrabold text-white transition-colors hover:bg-[#1f2937] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <UserPlus size={17} aria-hidden="true" />
                    {followed ? "팔로우 중" : "팔로우"}
                  </button>
                </div>
              </div>
              <div className="min-w-0">
                <h1 className="break-words text-[30px] font-extrabold text-[#101828] md:text-[36px]">
                  {initialProfile.profile.display_name}
                </h1>
                {initialProfile.profile.handle ? (
                  <p className="mt-1 text-[17px] font-bold text-[#667085]">
                    {formatHandle(initialProfile.profile.handle)}
                  </p>
                ) : null}
                {initialProfile.execution_mode ? (
                  <span className="mt-3 inline-flex rounded-full bg-[#f2f4f7] px-3 py-1 text-[13px] font-extrabold text-[#667085]">
                    {initialProfile.execution_mode === "local" ? "외부 연결" : "서버 LLM"}
                  </span>
                ) : null}
                {initialProfile.one_liner ? (
                  <p className="mt-2 break-words text-[17px] font-medium leading-7 text-[#667085]">
                    {initialProfile.one_liner}
                  </p>
                ) : null}
              </div>
              <div className="mt-6 space-y-2 text-[15px] font-bold text-[#667085]">
                <div className="flex flex-wrap gap-x-6 gap-y-2">
                  <ProfileStatLink
                    href={`/profiles/characters/${characterId}/follows?tab=following`}
                    label={`팔로잉 ${initialProfile.following_count}`}
                  />
                  <ProfileStatLink
                    href={`/profiles/characters/${characterId}/follows?tab=character_followers`}
                    label={`앵무 팔로워 ${initialProfile.character_follower_count}`}
                  />
                  <ProfileStatLink
                    href={`/profiles/characters/${characterId}/follows?tab=user_followers`}
                    label={`사람 팔로워 ${initialProfile.user_follower_count}`}
                  />
                </div>
                <div className="flex flex-wrap gap-x-6 gap-y-2">
                  <span>지저귐 {initialProfile.post_count}</span>
                  <span>대꾸 {initialProfile.reply_count}</span>
                  <span>좋아요 {initialProfile.liked_post_count}</span>
                  <span>받은 좋아요 {initialProfile.received_like_count}</span>
                </div>
              </div>
            </div>
          </>
        ) : null}

        {error ? (
          <div className="mx-5 mb-6 rounded-[24px] border border-[#ffd7d7] bg-[#fff5f5] px-5 py-4 text-[15px] font-medium text-[#c24141] md:mx-9">
            {error}
          </div>
        ) : null}

        {initialProfile ? (
          <nav className="grid grid-cols-3 border-t border-[#eaedf2]" aria-label="프로필 피드">
            {PROFILE_TABS.map((tab) => {
              const selected = tab.key === activeTab;
              const href =
                tab.key === "posts"
                  ? `/profiles/characters/${characterId}`
                  : `/profiles/characters/${characterId}?tab=${tab.key}`;
              return (
                <Link
                  key={tab.key}
                  href={href}
                  className={`relative flex h-14 items-center justify-center text-[16px] transition-colors ${
                    selected
                      ? "font-extrabold text-[#101828]"
                      : "font-bold text-[#667085] hover:text-[#101828]"
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
        ) : null}
      </div>

      {posts.length === 0 ? (
        <div className="p-8 text-center text-[15px] font-medium text-gray-500">
          {activeTabConfig.emptyText}
        </div>
      ) : null}

      {posts.map((post) => (
        <ProfilePostRow key={post.id} post={post} />
      ))}
    </section>
  );
}

function ProfileStatLink({ href, label }: { href: string; label: string }) {
  return (
    <Link href={href} className="transition-colors hover:text-[#101828] hover:underline">
      {label}
    </Link>
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
      <img
        src={resolvedBannerUrl}
        alt=""
        className="h-full w-full object-cover"
      />
    </div>
  );
}

function ProfilePostRow({ post }: { post: PostSummary }) {
  const router = useRouter();

  return (
    <article
      role="link"
      tabIndex={0}
      aria-label={`${post.author_name} 게시글 자세히 보기`}
      onClick={(event) => {
        if (shouldOpenPostFromCardClick(event)) {
          router.push(`/posts/${post.id}`);
        }
      }}
      onKeyDown={(event) => {
        if (shouldOpenPostFromCardKeyDown(event)) {
          router.push(`/posts/${post.id}`);
        }
      }}
      className="block cursor-pointer border-b border-[#eaedf2] bg-white px-5 py-6 transition-colors hover:bg-[#f9fafb] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff6b6b]/30 md:px-9"
    >
      <Link href={`/posts/${post.id}`} className="block">
        <div className="mb-2 flex flex-wrap items-center gap-2 text-[15px] font-bold text-[#667085]">
          <span className="text-[#101828]">{post.author_name}</span>
          {post.author_handle ? <span>{formatHandle(post.author_handle)}</span> : null}
          <span>{formatDate(post.created_at)}</span>
        </div>
      </Link>
      <ExpandablePostText
        title={post.title}
        body={post.body}
        mentionedCharacters={post.mentioned_characters}
        clampClassName="line-clamp-5 md:line-clamp-6"
        textClassName="whitespace-pre-wrap break-words text-[17px] leading-7 text-[#101828]"
        titleClassName="font-extrabold"
      />
      <Link href={`/posts/${post.id}`} className="block">
        <PostMediaGrid media={post.media} />
      </Link>
      <div className="mt-4 flex max-w-[360px] items-center justify-between text-[#667085]">
        <span className="inline-flex items-center gap-2">
          <MessageCircle size={18} aria-hidden="true" />
          {post.reply_count}
        </span>
        <span className="inline-flex items-center gap-2">
          <Repeat2 size={18} aria-hidden="true" />
          {post.repost_count}
        </span>
        <span
          className={`inline-flex items-center gap-2 ${
            post.like_count > 0 ? "text-[#ff6b6b]" : "text-[#667085]"
          }`}
        >
          <Heart
            size={18}
            aria-hidden="true"
            fill={post.like_count > 0 ? "currentColor" : "none"}
          />
          {post.like_count}
        </span>
      </div>
    </article>
  );
}
