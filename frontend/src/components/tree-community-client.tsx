"use client";

import { MessageCircle, RefreshCw, Send } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import type { FormEvent } from "react";

import { ProfileAvatar } from "@/components/profile-avatar";
import {
  hasStoredAuth,
  listAgents,
  type AgentDetailRead,
  type UserRead,
} from "@/lib/agents";
import { formatDate } from "@/lib/community";
import {
  createTreePost,
  listTreePosts,
  type TreeCategory,
  type TreeFeedPage,
  type TreePostDetail,
  type TreePostSummary,
} from "@/lib/tree";
import { isOfficialOperatorName } from "@/lib/profile";
import { useMobilePullToRefresh } from "@/lib/use-mobile-pull-to-refresh";

const TABS: { category: TreeCategory; label: string }[] = [
  { category: "notice", label: "공지" },
  { category: "bug", label: "버그" },
  { category: "suggestion", label: "제안" },
  { category: "question", label: "질문" },
  { category: "free", label: "잡담" },
];

const PLACEHOLDER_BY_CATEGORY: Record<Exclude<TreeCategory, "notice">, string> = {
  bug: "발견한 문제를 적어주세요",
  suggestion: "개선 아이디어를 적어주세요",
  question: "궁금한 점을 적어주세요",
  free: "자유롭게 이야기해보세요",
};

const BUTTON_BY_CATEGORY: Record<Exclude<TreeCategory, "notice">, string> = {
  bug: "버그 제보",
  suggestion: "제안하기",
  question: "질문하기",
  free: "글쓰기",
};

export function TreeCommunityClient({
  initialPage,
  initialCategory,
  initialQuery,
  initialError,
}: {
  initialPage: TreeFeedPage;
  initialCategory: TreeCategory;
  initialQuery: string;
  initialError: string | null;
}) {
  const [posts, setPosts] = useState(initialPage.items);
  const [nextCursor, setNextCursor] = useState(initialPage.next_cursor);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(initialError);
  const [composerText, setComposerText] = useState("");
  const [composerError, setComposerError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const user = useSyncExternalStore(
    subscribeToStoredUser,
    getStoredUserSnapshot,
    getServerUserSnapshot,
  );
  const [agents, setAgents] = useState<AgentDetailRead[]>([]);
  const [relatedCharacterId, setRelatedCharacterId] = useState("");

  const loadPage = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await listTreePosts({
        category: initialCategory,
        query: initialQuery,
        limit: 10,
      });
      setPosts(page.items);
      setNextCursor(page.next_cursor);
    } catch (err) {
      setError(err instanceof Error ? err.message : "나무 글을 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, [initialCategory, initialQuery]);

  useMobilePullToRefresh({
    refreshing: loading,
    onRefresh: loadPage,
  });

  useEffect(() => {
    if (!hasStoredAuth()) return;
    listAgents()
      .then(setAgents)
      .catch(() => setAgents([]));
  }, []);

  async function loadMore() {
    if (!nextCursor || loading) return;
    setLoading(true);
    setError(null);
    try {
      const page = await listTreePosts({
        category: initialCategory,
        query: initialQuery,
        cursor: nextCursor,
        limit: 10,
      });
      setPosts((previous) => [...previous, ...page.items]);
      setNextCursor(page.next_cursor);
    } catch (err) {
      setError(err instanceof Error ? err.message : "나무 글을 더 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (initialCategory === "notice") return;
    const content = composerText.trim();
    if (!hasStoredAuth()) {
      setComposerError("로그인 후 글을 쓸 수 있습니다.");
      return;
    }
    if (content.length < 2) {
      setComposerError("두 글자 이상 적어주세요.");
      return;
    }

    setSaving(true);
    setComposerError(null);
    try {
      const detail = await createTreePost({
        category: initialCategory,
        title: deriveTitle(content),
        body: content,
        related_character_id:
          initialCategory === "bug" && relatedCharacterId ? relatedCharacterId : null,
      });
      setPosts((previous) => [detailToSummary(detail), ...previous]);
      setComposerText("");
      setRelatedCharacterId("");
    } catch (err) {
      setComposerError(err instanceof Error ? err.message : "글을 저장하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  }

  const showComposer = initialCategory !== "notice";

  return (
    <section className="flex min-h-screen w-full flex-col bg-white">
      <div className="sticky top-0 z-10 flex min-h-[72px] flex-wrap items-center justify-between gap-3 border-b border-[#eaedf2] bg-white/95 px-5 py-4 backdrop-blur-sm md:min-h-[88px] md:px-9">
        <h1 className="text-[28px] font-extrabold text-[#101828] md:text-[30px]">나무</h1>
        <div className="-mx-5 flex w-[calc(100%+2.5rem)] items-center gap-2 overflow-x-auto px-5 pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden md:mx-0 md:w-auto md:flex-wrap md:px-0 md:pb-0">
          {TABS.map((tab) => (
            <Link
              key={tab.category}
              href={treeTabHref(tab.category, initialQuery)}
              className={treeTabClass(initialCategory === tab.category)}
              aria-current={initialCategory === tab.category ? "page" : undefined}
            >
              {tab.label}
            </Link>
          ))}
          <button
            type="button"
            onClick={loadPage}
            disabled={loading}
            className="hidden size-10 items-center justify-center rounded-full border border-[#e1e5eb] bg-white text-[#667085] transition-colors hover:bg-[#f9fafb] disabled:cursor-not-allowed disabled:opacity-60 md:inline-flex"
            title="새로고침"
          >
            <RefreshCw size={18} aria-hidden="true" />
          </button>
        </div>
      </div>

      {showComposer ? (
        <TreeComposer
          category={initialCategory}
          text={composerText}
          user={user}
          agents={agents}
          relatedCharacterId={relatedCharacterId}
          saving={saving}
          error={composerError}
          onTextChange={setComposerText}
          onRelatedCharacterChange={setRelatedCharacterId}
          onSubmit={handleSubmit}
        />
      ) : null}

      {initialQuery ? (
        <div className="border-b border-[#eaedf2] bg-[#f9fafb] px-5 py-3 text-[14px] font-bold text-[#667085] md:px-9">
          나무 검색: <span className="text-[#101828]">{initialQuery}</span>
        </div>
      ) : null}

      {error ? (
        <div className="m-6 rounded-xl border border-red-200 bg-red-50 px-6 py-4 text-sm text-red-600">
          {error}
        </div>
      ) : null}

      {!error && posts.length === 0 ? (
        <div className="p-8 text-center text-[15px] font-medium text-gray-500">
          {emptyText(initialCategory, initialQuery)}
        </div>
      ) : null}

      <div className="flex flex-col">
        {posts.map((post) => (
          <TreePostRow key={post.id} post={post} />
        ))}
      </div>

      {nextCursor ? (
        <div className="px-5 py-6 md:px-9">
          <button
            type="button"
            onClick={loadMore}
            disabled={loading}
            className="h-12 w-full rounded-full border border-[#e1e5eb] bg-white text-[15px] font-extrabold text-[#667085] transition-colors hover:bg-[#f9fafb] disabled:cursor-not-allowed disabled:opacity-60"
          >
            더 보기
          </button>
        </div>
      ) : null}
    </section>
  );
}

function TreeComposer({
  category,
  text,
  user,
  agents,
  relatedCharacterId,
  saving,
  error,
  onTextChange,
  onRelatedCharacterChange,
  onSubmit,
}: {
  category: Exclude<TreeCategory, "notice">;
  text: string;
  user: UserRead | null;
  agents: AgentDetailRead[];
  relatedCharacterId: string;
  saving: boolean;
  error: string | null;
  onTextChange: (value: string) => void;
  onRelatedCharacterChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const placeholder = PLACEHOLDER_BY_CATEGORY[category];
  const buttonLabel = BUTTON_BY_CATEGORY[category];

  return (
    <form onSubmit={onSubmit} className="border-b border-[#eaedf2] bg-white px-5 py-5 md:px-9">
      <div className="flex gap-4 md:gap-6">
        <div className="shrink-0">
          {user ? (
            <ProfileAvatar
              name={user.display_name}
              avatarUrl={null}
              sizeClassName="size-[52px] md:size-[58px]"
              textClassName="text-[22px]"
            />
          ) : (
            <div className="size-[52px] rounded-full border border-[#e1e5eb] bg-[#f3f4f6] md:size-[58px]" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex min-w-0 flex-wrap items-center gap-x-2 text-[15px] font-bold text-[#667085]">
            <span className={composerAuthorNameClass(user?.display_name)}>
              {user?.display_name ?? "로그인이 필요합니다"}
            </span>
          </div>

          <textarea
            value={text}
            onChange={(event) => onTextChange(event.target.value)}
            disabled={saving}
            maxLength={4000}
            rows={3}
            placeholder={placeholder}
            className="min-h-[86px] w-full resize-none rounded-[18px] border border-[#e1e5eb] bg-white px-4 py-3 text-[15px] font-medium leading-6 text-[#101828] outline-none transition-colors placeholder:text-[#98a2b3] focus:border-[#ff8a8a] disabled:cursor-not-allowed disabled:bg-[#f3f4f6] disabled:text-[#98a2b3]"
          />

          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex min-h-10 flex-1 items-center gap-2 text-[13px] font-bold">
              {category === "bug" && agents.length > 0 ? (
                <select
                  value={relatedCharacterId}
                  onChange={(event) => onRelatedCharacterChange(event.target.value)}
                  className="h-10 max-w-full rounded-full border border-[#e1e5eb] bg-white px-3 text-[13px] font-bold text-[#667085] outline-none focus:border-[#ff8a8a]"
                >
                  <option value="">관련 앵무 선택 안 함</option>
                  {agents.map((agent) => (
                    <option key={agent.character.id} value={agent.character.id}>
                      {agent.character.name}
                    </option>
                  ))}
                </select>
              ) : null}
              {error ? <span className="text-[#c24141]">{error}</span> : null}
            </div>
            <button
              type="submit"
              disabled={saving || text.trim().length < 2}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-full bg-[#101828] px-5 text-[14px] font-extrabold text-white transition-colors hover:bg-[#1d2939] disabled:cursor-not-allowed disabled:bg-[#c9ced6]"
            >
              <Send size={16} />
              {saving ? "저장 중" : buttonLabel}
            </button>
          </div>
        </div>
      </div>
    </form>
  );
}

function TreePostRow({ post }: { post: TreePostSummary }) {
  const authorHref = `/profiles/users/${post.author.id}`;

  return (
    <article className="group border-b border-[#eaedf2] bg-white px-5 py-7 transition-colors hover:bg-[#f9fafb] md:px-9 md:py-8">
      <div className="flex gap-3 md:gap-6">
        <Link href={authorHref} className="shrink-0 rounded-full" aria-label={`${post.author.display_name} profile`}>
          <ProfileAvatar
            name={post.author.display_name}
            avatarUrl={post.author.avatar_url}
            sizeClassName="size-12 md:size-[58px]"
            textClassName="text-[18px] md:text-[24px]"
          />
        </Link>
        <div className="min-w-0 flex-1 overflow-hidden">
          <div>
            <div className="mb-2 flex min-w-0 flex-wrap items-center gap-x-2 text-[16px] md:text-[18px]">
              <span className="rounded-full bg-[#fff0ef] px-3 py-1 text-[13px] font-extrabold text-[#ff6b6b]">
                {categoryLabel(post.category)}
              </span>
              <Link href={authorHref} className={treeAuthorNameClass(post.author.display_name)}>
                {post.author.display_name}
              </Link>
              <span className="font-medium text-[#667085]">·</span>
              <span className="font-medium text-[#667085]">{formatDate(post.created_at)}</span>
            </div>
            {post.related_character ? (
              <div className="mb-2 text-[13px] font-bold text-[#98a2b3]">
                관련 앵무: {post.related_character.name}
              </div>
            ) : null}
            <Link href={`/tree/${post.id}`} className="block">
              <p className="line-clamp-4 whitespace-pre-wrap break-all text-[18px] leading-[1.55] text-[#101828] md:break-words md:text-[22px] md:leading-[1.5]">
                <span className="font-bold">{post.title}</span>
                {post.body === post.title ? "" : ` ${post.body}`}
              </p>
            </Link>
          </div>
          <div className="mt-6 flex w-full max-w-[220px] items-center text-[#667085]">
            <Link
              href={`/tree/${post.id}`}
              className="flex items-center gap-2 transition-colors hover:text-[#ff6b6b]"
              title="댓글"
            >
              <span className="rounded-full p-1.5 transition-colors hover:bg-[#ff6b6b]/10">
                <MessageCircle className="size-[22px] md:size-[25px]" strokeWidth={1.6} />
              </span>
              <span className="text-[16px] font-medium md:text-[18px]">
                {post.comment_count}
              </span>
            </Link>
          </div>
        </div>
      </div>
    </article>
  );
}

function detailToSummary(detail: TreePostDetail): TreePostSummary {
  return {
    id: detail.id,
    category: detail.category,
    title: detail.title,
    body: detail.body,
    author: detail.author,
    related_character: detail.related_character,
    comment_count: detail.comments.length,
    created_at: detail.created_at,
    updated_at: detail.updated_at,
  };
}

function deriveTitle(content: string) {
  const firstLine = content.split(/\r?\n/, 1)[0]?.trim() ?? "";
  return (firstLine || content).slice(0, 80);
}

function treeTabHref(category: TreeCategory, query: string) {
  const params = new URLSearchParams({ tab: category });
  if (query.trim()) params.set("q", query.trim());
  return `/tree?${params.toString()}`;
}

function treeTabClass(active: boolean) {
  return `inline-flex h-10 shrink-0 items-center rounded-full border px-4 text-[14px] font-extrabold whitespace-nowrap break-keep transition-colors ${
    active
      ? "border-[#ffb5b5] bg-[#fff0ef] text-[#ff6b6b]"
      : "border-[#e1e5eb] bg-white text-[#101828] hover:bg-[#f9fafb]"
  }`;
}

function categoryLabel(category: TreeCategory) {
  return TABS.find((tab) => tab.category === category)?.label ?? category;
}

function composerAuthorNameClass(name?: string | null) {
  return `truncate ${isOfficialOperatorName(name) ? "text-[#ff6b6b]" : "text-[#101828]"}`;
}

function treeAuthorNameClass(name?: string | null) {
  return `font-extrabold hover:underline ${isOfficialOperatorName(name) ? "text-[#ff6b6b]" : "text-[#101828]"}`;
}

function emptyText(category: TreeCategory, query: string) {
  if (query.trim()) return "검색 결과가 없습니다.";
  if (category === "notice") return "아직 공지가 없습니다.";
  return "아직 올라온 나무 글이 없습니다.";
}

let cachedUserRaw: string | null = null;
let cachedUser: UserRead | null = null;

function getStoredUserSnapshot() {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem("angmoo.user");
  if (raw === cachedUserRaw) return cachedUser;
  cachedUserRaw = raw;
  if (!raw) {
    cachedUser = null;
    return cachedUser;
  }
  try {
    cachedUser = JSON.parse(raw) as UserRead;
  } catch {
    cachedUser = null;
  }
  return cachedUser;
}

function getServerUserSnapshot(): UserRead | null {
  return null;
}

function subscribeToStoredUser(onStoreChange: () => void) {
  window.addEventListener("storage", onStoreChange);
  return () => window.removeEventListener("storage", onStoreChange);
}
