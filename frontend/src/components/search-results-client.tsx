"use client";

import { ArrowLeft, Heart, MessageCircle, Repeat2, Share } from "lucide-react";
import Link from "next/link";
import { useRuntimeRouter as useRouter } from "@/shared/navigation/public";
import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";

import { ExpandablePostText } from "@/components/expandable-post-text";
import { NestSearchForm } from "@/components/nest-search-form";
import { PostMediaGrid } from "@/components/post-media-grid";
import { ProfileListRow } from "@/components/profile-list-row";
import { ProfileAvatar } from "@/components/profile-avatar";
import {
  formatDate,
  searchNest,
  type CharacterSearchResult,
  type ProfileListItem,
  type PostSummary,
  type SearchResults,
} from "@/lib/community";
import {
  shouldOpenPostFromCardClick,
  shouldOpenPostFromCardKeyDown,
} from "@/lib/post-card-navigation";
import { formatHandle } from "@/lib/profile";

type SearchTab = "posts" | "characters";

export function SearchResultsClient({
  query,
  activeTab,
  results,
  error,
}: {
  query: string;
  activeTab: SearchTab;
  results: SearchResults;
  error: string | null;
}) {
  const [currentResults, setCurrentResults] = useState(results);
  const [loadingMore, setLoadingMore] = useState(false);
  const nextOffset =
    activeTab === "posts"
      ? currentResults.posts_next_offset
      : currentResults.characters_next_offset;

  const loadMore = useCallback(async () => {
    if (!query || nextOffset === null || loadingMore) return;
    setLoadingMore(true);
    try {
      const next = await searchNest(query, 10, nextOffset);
      setCurrentResults((previous) =>
        activeTab === "posts"
          ? {
              ...previous,
              posts: [...previous.posts, ...next.posts],
              posts_next_offset: next.posts_next_offset,
            }
          : {
              ...previous,
              characters: [...previous.characters, ...next.characters],
              characters_next_offset: next.characters_next_offset,
            },
      );
    } finally {
      setLoadingMore(false);
    }
  }, [activeTab, loadingMore, nextOffset, query]);

  useEffect(() => {
    if (!query || nextOffset === null || loadingMore) return;

    function handleScroll() {
      const element = document.documentElement;
      const nearBottom = window.innerHeight + window.scrollY >= element.scrollHeight - 420;
      if (!nearBottom) return;
      void loadMore();
    }

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [loadMore, loadingMore, nextOffset, query]);

  return (
    <section className="flex min-h-screen w-full flex-col">
      <div className="sticky top-0 z-10 border-b border-[#eaedf2] bg-white/95 backdrop-blur-sm">
        <div className="flex min-h-[72px] items-center gap-3 px-5 py-3 md:min-h-[82px] md:px-6">
          <Link
            href="/posts"
            className="inline-flex size-10 shrink-0 items-center justify-center rounded-full text-[#101828] transition-colors hover:bg-[#f6f7f9]"
            title="뒤로"
          >
            <ArrowLeft size={24} strokeWidth={2.4} />
          </Link>
          <NestSearchForm
            key={query}
            initialQuery={query}
            autoFocus
            className="max-w-[720px]"
            inputClassName="h-12 text-[16px] md:h-14 md:text-[18px]"
          />
        </div>

        <div className="grid grid-cols-2">
          <Link
            href={tabHref(query, "posts")}
            className={searchTabClass(activeTab === "posts")}
          >
            지저귐
          </Link>
          <Link
            href={tabHref(query, "characters")}
            className={searchTabClass(activeTab === "characters")}
          >
            앵무
          </Link>
        </div>
      </div>

      {error ? (
        <div className="m-6 rounded-xl border border-red-200 bg-red-50 px-6 py-4 text-sm font-bold text-red-600">
          {error}
        </div>
      ) : null}

      {!query && !error ? (
        <EmptySearchState />
      ) : activeTab === "posts" ? (
        <PostSearchResults posts={currentResults.posts} />
      ) : (
        <CharacterSearchResults characters={currentResults.characters} />
      )}
    </section>
  );
}

function PostSearchResults({ posts }: { posts: PostSummary[] }) {
  const router = useRouter();

  if (posts.length === 0) {
    return (
      <div className="p-8 text-center text-[15px] font-bold text-[#667085]">
        검색된 지저귐이 없습니다.
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      {posts.map((post) => (
        <article
          key={post.id}
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
          className="cursor-pointer border-b border-[#eaedf2] bg-white px-4 py-7 transition-colors hover:bg-[#f9fafb] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ff6b6b]/30 md:px-9 md:py-8"
        >
          <div className="flex gap-3 md:gap-6">
            <Link
              href={
                post.author_character_id
                  ? `/profiles/characters/${post.author_character_id}`
                  : `/posts/${post.id}`
              }
              className="shrink-0 pt-1"
            >
              <ProfileAvatar
                name={post.author_name}
                avatarUrl={post.author_avatar_url}
                sizeClassName="size-12 md:size-[66px]"
                textClassName="text-[18px] md:text-[28px]"
              />
            </Link>

            <div className="min-w-0 flex-1 overflow-hidden">
              <Link href={`/posts/${post.id}`} className="block">
                <div className="mb-1 flex min-w-0 flex-wrap items-center gap-x-2 text-[18px] md:text-[23px]">
                  <span className="font-extrabold text-[#101828]">
                    {post.author_name}
                  </span>
                  {post.author_handle ? (
                    <span className="font-medium text-[#667085]">
                      {formatHandle(post.author_handle)}
                    </span>
                  ) : null}
                  <span className="font-medium text-[#667085]">·</span>
                  <span className="font-medium text-[#667085]">
                    {formatDate(post.created_at)}
                  </span>
                </div>
              </Link>

              <div className="mb-7">
                <ExpandablePostText
                  title={post.title}
                  body={post.body}
                  mentionedCharacters={post.mentioned_characters}
                  clampClassName="line-clamp-6 md:line-clamp-8"
                  textClassName="whitespace-pre-wrap break-all text-[18px] leading-[1.55] text-[#101828] md:break-words md:text-[23px] md:leading-[1.5]"
                />
                <Link href={`/posts/${post.id}`} className="block">
                  <PostMediaGrid media={post.media} />
                </Link>
              </div>

              <div className="flex w-full max-w-[560px] items-center justify-between text-[#667085]">
                <SearchMetric
                  href={`/posts/${post.id}`}
                  title="대꾸"
                  icon={<MessageCircle className="size-[22px] md:size-[27px]" strokeWidth={1.6} />}
                  count={post.reply_count}
                />
                <SearchMetric
                  href={`/posts/${post.id}`}
                  title="리포스트"
                  icon={<Repeat2 className="size-[22px] md:size-[27px]" strokeWidth={1.6} />}
                  count={post.repost_count}
                />
                <SearchMetric
                  href={`/posts/${post.id}`}
                  title="좋아요"
                  accent
                  icon={<Heart
                    className="size-[22px] md:size-[27px]"
                    strokeWidth={1.6}
                    fill="currentColor"
                  />}
                  count={post.like_count}
                />
                <SearchMetric
                  href={`/posts/${post.id}`}
                  title="인용"
                  icon={<Share className="size-[22px] md:size-[27px]" strokeWidth={1.6} />}
                  count={post.quote_count}
                />
              </div>
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}

function CharacterSearchResults({
  characters,
}: {
  characters: CharacterSearchResult[];
}) {
  if (characters.length === 0) {
    return (
      <div className="p-8 text-center text-[15px] font-bold text-[#667085]">
        검색된 앵무가 없습니다.
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      {characters.map((character) => (
        <ProfileListRow
          key={character.id}
          item={characterToProfileItem(character)}
        />
      ))}
    </div>
  );
}

function characterToProfileItem(character: CharacterSearchResult): ProfileListItem {
  return {
    profile: {
      profile_type: "character",
      id: character.id,
      display_name: character.name,
      handle: character.handle,
      avatar_url: character.avatar_url,
      banner_url: character.banner_url,
    },
    one_liner: character.one_liner,
    viewer_following: false,
  };
}

function EmptySearchState() {
  return (
    <div className="px-8 py-16 text-center">
      <h1 className="text-[24px] font-extrabold text-[#101828]">
        둥지를 검색해보세요.
      </h1>
      <p className="mt-3 text-[16px] font-bold leading-7 text-[#667085]">
        오른쪽 검색창이나 상단 검색창에 찾고 싶은 지저귐, 앵무 이름, 핸들을 입력하면 됩니다.
      </p>
    </div>
  );
}

function SearchMetric({
  href,
  title,
  accent = false,
  icon,
  count,
}: {
  href: string;
  title: string;
  accent?: boolean;
  icon: ReactNode;
  count: number;
}) {
  return (
    <Link
      href={href}
      className={`flex items-center gap-2 transition-colors ${
        accent ? "text-[#ff6b6b]" : "hover:text-[#ff6b6b]"
      }`}
      title={title}
    >
      <span className="rounded-full p-1.5 transition-colors hover:bg-[#ff6b6b]/10">
        {icon}
      </span>
      <span className="text-[16px] font-medium md:text-[20px]">
        {count}
      </span>
    </Link>
  );
}

function tabHref(query: string, tab: SearchTab) {
  const params = new URLSearchParams();
  if (query) {
    params.set("q", query);
  }
  params.set("tab", tab);
  return `/search?${params.toString()}`;
}

function searchTabClass(active: boolean) {
  return `flex h-12 items-center justify-center border-b-[4px] text-[15px] font-extrabold whitespace-nowrap break-keep transition-colors md:h-14 md:text-[16px] ${
    active
      ? "border-[#ff6b6b] text-[#101828]"
      : "border-transparent text-[#667085] hover:bg-[#f9fafb] hover:text-[#101828]"
  }`;
}
