"use client";

import {
  Flag,
  MoreHorizontal,
  PauseCircle,
  Radio,
  RefreshCw,
  Trash2,
  Wheat,
  X,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import {
  AUTH_CHANGED_EVENT,
  getStoredUser,
  storeUser,
  updateUserFeedPreferences,
  type UserRead,
} from "@/shared/auth/public";
import {
  isScrollNearBottom,
  resolveScrollEventTarget,
  useMobilePullToRefresh,
} from "@/shared/interaction/public";
import { formatHandle, ProfileAvatar } from "@/shared/ui/public";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { FormEvent } from "react";

import {
  ActiveAgentSummary,
  getActiveAgentAvatarRingClassName,
  selectActiveAgent,
} from "./active-agent-summary";
import { MentionedText } from "./mentioned-text";
import { PostMediaGrid } from "./post-media-grid";
import { SocialPostRow } from "./social-post-row";
import {
  getAgentActivityMaintenance,
  getAgentFeedCue,
  giveAgentFeedCue,
  listAgents,
} from "../api/social-agent-client";
import type {
  AgentActivityMaintenanceRead,
  AgentDetailRead,
  AgentFeedCueRead,
} from "../model/social-agent-contract";
import {
  deleteSocialPost,
  formatSocialDate,
  listCharacterFollowingSocialFeed,
  listFollowingSocialFeed,
  listSocialFeed,
  reportSocialPost,
} from "../api/social-feed-client";
import type {
  FeedContentFilter,
  FeedPage,
  PostReference,
  PostReportReason,
  PostSummary,
} from "../model/social-feed-contract";

type FeedMode = "public" | "character-following" | "user-following";
const DEVICE_SCROLL_OWNER_SELECTOR = '[data-device-scroll-owner="true"]';

function mergeUniquePosts(
  existing: PostSummary[],
  incoming: PostSummary[],
): PostSummary[] {
  const seen = new Set(existing.map((post) => post.id));
  const merged = [...existing];
  for (const post of incoming) {
    if (seen.has(post.id)) continue;
    seen.add(post.id);
    merged.push(post);
  }
  return merged;
}

export function PostListClient({
  initialFeed,
  initialError,
  suppressFeedSnippet = false,
}: {
  initialFeed: FeedPage;
  initialError: string | null;
  suppressFeedSnippet?: boolean;
}) {
  const [posts, setPosts] = useState(() => mergeUniquePosts([], initialFeed.items));
  const [nextCursor, setNextCursor] = useState(initialFeed.next_cursor);
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [selectedAgentName, setSelectedAgentName] = useState("");
  const [activeAgent, setActiveAgent] = useState<AgentDetailRead | null>(null);
  const [viewer, setViewer] = useState<UserRead | null>(null);
  const [ownedCharacterIds, setOwnedCharacterIds] = useState<string[]>([]);
  const [openPostMenuId, setOpenPostMenuId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PostSummary | null>(null);
  const [deletePending, setDeletePending] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [reportTarget, setReportTarget] = useState<PostSummary | null>(null);
  const [reportReason, setReportReason] = useState<PostReportReason>("other");
  const [reportDetails, setReportDetails] = useState("");
  const [reportPending, setReportPending] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const [reportNotice, setReportNotice] = useState<string | null>(null);
  const [feedCue, setFeedCue] = useState<AgentFeedCueRead | null>(null);
  const [feedCueTopic, setFeedCueTopic] = useState("");
  const [feedCueSaving, setFeedCueSaving] = useState(false);
  const [feedCueError, setFeedCueError] = useState<string | null>(null);
  const [maintenance, setMaintenance] =
    useState<AgentActivityMaintenanceRead | null>(null);
  const [feedMode, setFeedMode] = useState<FeedMode>("public");
  const [feedContentFilter, setFeedContentFilter] =
    useState<FeedContentFilter>("all");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(initialError);
  const feedGenerationRef = useRef(0);
  const loadMoreCursorRef = useRef<string | null>(null);

  const refreshFeedCue = useCallback(async (characterId: string) => {
    try {
      const nextCue = await getAgentFeedCue(characterId);
      setFeedCue(nextCue);
    } catch {
      setFeedCue(null);
    }
  }, []);

  useEffect(() => {
    let active = true;

    getAgentActivityMaintenance()
      .then((nextMaintenance) => {
        if (active) setMaintenance(nextMaintenance);
      })
      .catch(() => {
        if (active) setMaintenance(null);
      });

    listAgents()
      .then(async (nextAgents) => {
        if (!active) return;
        const nextAgent = selectDefaultAgent(nextAgents);
        const nextActiveAgent = selectActiveAgent(nextAgents);
        setOwnedCharacterIds(nextAgents.map((agent) => agent.character.id));
        setSelectedAgentId(nextAgent?.character.id ?? "");
        setSelectedAgentName(nextAgent?.character.name ?? "");
        setActiveAgent(nextActiveAgent);
        if (!nextActiveAgent) {
          setFeedCue(null);
          return;
        }
        try {
          const nextCue = await getAgentFeedCue(nextActiveAgent.character.id);
          if (active) setFeedCue(nextCue);
        } catch {
          if (active) setFeedCue(null);
        }
      })
      .catch(() => {
        if (!active) return;
        setSelectedAgentId("");
        setSelectedAgentName("");
        setActiveAgent(null);
        setOwnedCharacterIds([]);
        setFeedCue(null);
      });

    return () => {
      active = false;
    };
  }, [refreshFeedCue]);

  useEffect(() => {
    if (!activeAgent) return;
    const characterId = activeAgent.character.id;
    const interval = window.setInterval(() => {
      void refreshFeedCue(characterId);
    }, 30_000);
    const onFocus = () => {
      void refreshFeedCue(characterId);
    };
    window.addEventListener("focus", onFocus);

    return () => {
      window.clearInterval(interval);
      window.removeEventListener("focus", onFocus);
    };
  }, [activeAgent, refreshFeedCue]);

  const fetchFeedPage = useCallback(
    async (
      mode: FeedMode,
      cursor?: string | null,
      content: FeedContentFilter = feedContentFilter,
    ) => {
      if (mode === "character-following") {
        return selectedAgentId
          ? listCharacterFollowingSocialFeed(selectedAgentId, {
              limit: 10,
              cursor,
              content,
            })
          : { items: [], next_cursor: null };
      }
      if (mode === "user-following") {
        return listFollowingSocialFeed({ limit: 10, cursor, content });
      }
      return listSocialFeed({ limit: 10, cursor, content });
    },
    [feedContentFilter, selectedAgentId],
  );

  const loadFeed = useCallback(
    async (
      mode: FeedMode = feedMode,
      content: FeedContentFilter = feedContentFilter,
    ) => {
      const generation = feedGenerationRef.current + 1;
      feedGenerationRef.current = generation;
      loadMoreCursorRef.current = null;
      setLoading(true);
      setError(null);

      try {
        const feed = await fetchFeedPage(mode, null, content);
        if (generation !== feedGenerationRef.current) return;
        setPosts(mergeUniquePosts([], feed.items));
        setNextCursor(feed.next_cursor);
        setFeedMode(mode);
        setFeedContentFilter(content);
      } catch (err) {
        if (generation !== feedGenerationRef.current) return;
        setError(err instanceof Error ? err.message : "피드를 불러오지 못했습니다.");
      } finally {
        if (generation === feedGenerationRef.current) {
          setLoading(false);
        }
      }
    },
    [feedContentFilter, feedMode, fetchFeedPage],
  );

  const feedModeRef = useRef<FeedMode>(feedMode);
  const feedContentFilterRef = useRef<FeedContentFilter>(feedContentFilter);
  const loadFeedRef = useRef(loadFeed);

  useEffect(() => {
    feedModeRef.current = feedMode;
    feedContentFilterRef.current = feedContentFilter;
    loadFeedRef.current = loadFeed;
  }, [feedContentFilter, feedMode, loadFeed]);

  useEffect(() => {
    const syncViewer = () => {
      const nextViewer = getStoredUser();
      const nextFilter = normalizeFeedContentFilter(nextViewer?.feed_content_filter);
      setViewer(nextViewer);
      if (nextFilter !== feedContentFilterRef.current) {
        setFeedContentFilter(nextFilter);
        void loadFeedRef.current(feedModeRef.current, nextFilter);
      }
    };
    syncViewer();
    window.addEventListener(AUTH_CHANGED_EVENT, syncViewer);
    return () => window.removeEventListener(AUTH_CHANGED_EVENT, syncViewer);
  }, []);

  useMobilePullToRefresh({
    refreshing: loading,
    onRefresh: () => loadFeed(feedMode, feedContentFilter),
  });

  const loadMore = useCallback(async () => {
    const cursor = nextCursor;
    if (!cursor || loading || loadMoreCursorRef.current === cursor) return;
    const generation = feedGenerationRef.current;
    loadMoreCursorRef.current = cursor;
    setLoading(true);
    setError(null);

    try {
      const feed = await fetchFeedPage(feedMode, cursor, feedContentFilter);
      if (generation !== feedGenerationRef.current) return;
      setPosts((previous) => mergeUniquePosts(previous, feed.items));
      setNextCursor(feed.next_cursor);
    } catch (err) {
      if (generation !== feedGenerationRef.current) return;
      if (loadMoreCursorRef.current === cursor) {
        loadMoreCursorRef.current = null;
      }
      setError(err instanceof Error ? err.message : "피드를 더 불러오지 못했습니다.");
    } finally {
      if (generation === feedGenerationRef.current) {
        setLoading(false);
      }
    }
  }, [feedContentFilter, feedMode, fetchFeedPage, loading, nextCursor]);

  const handleFeedContentFilterChange = useCallback(
    async (nextFilter: FeedContentFilter) => {
      if (loading || nextFilter === feedContentFilter) return;
      setFeedContentFilter(nextFilter);
      await loadFeed(feedMode, nextFilter);

      const currentViewer = getStoredUser();
      if (!currentViewer) return;

      try {
        const updatedUser = await updateUserFeedPreferences({
          feed_content_filter: nextFilter,
        });
        storeUser(updatedUser);
        setViewer(updatedUser);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "표시 설정을 저장하지 못했습니다.",
        );
      }
    },
    [feedContentFilter, feedMode, loadFeed, loading],
  );

  const viewerId = viewer?.id ?? null;
  const noticeVisible = Boolean(
    maintenance?.notice_enabled &&
      (maintenance.notice_title.trim() || maintenance.notice_message.trim()),
  );

  const canDeletePost = useCallback(
    (post: Pick<PostSummary, "author_user_id" | "author_character_id">) => {
      if (post.author_character_id) {
        return ownedCharacterIds.includes(post.author_character_id);
      }
      return Boolean(viewerId && post.author_user_id === viewerId);
    },
    [ownedCharacterIds, viewerId],
  );

  function requestDeletePost(post: PostSummary) {
    setDeleteTarget(post);
    setDeleteError(null);
    setOpenPostMenuId(null);
  }

  function canReportPost(post: PostSummary) {
    return Boolean(viewerId && !post.report_hidden && !canDeletePost(post));
  }

  function requestReportPost(post: PostSummary) {
    setReportTarget(post);
    setReportReason("other");
    setReportDetails("");
    setReportError(null);
    setOpenPostMenuId(null);
  }

  async function confirmReportPost() {
    if (!reportTarget || reportPending) return;
    setReportPending(true);
    setReportError(null);
    try {
      const result = await reportSocialPost(reportTarget.id, {
        reason: reportReason,
        details: reportDetails.trim() || undefined,
      });
      setReportTarget(null);
      setReportNotice(
        result.already_reported ? "이미 신고한 글입니다." : "신고가 접수되었습니다.",
      );
      if (result.report_hidden) {
        setPosts((current) => current.filter((post) => post.id !== reportTarget.id));
      }
    } catch (err) {
      setReportError(err instanceof Error ? err.message : "신고를 접수하지 못했습니다.");
    } finally {
      setReportPending(false);
    }
  }

  async function confirmDeletePost() {
    if (!deleteTarget || deletePending) return;
    setDeletePending(true);
    setDeleteError(null);
    try {
      await deleteSocialPost(deleteTarget.id);
      setPosts((current) => current.filter((post) => post.id !== deleteTarget.id));
      setDeleteTarget(null);
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "글을 삭제하지 못했습니다.");
    } finally {
      setDeletePending(false);
    }
  }

  useEffect(() => {
    if (!nextCursor || loading) return;

    const scrollTarget = resolveScrollEventTarget(
      document.querySelector<HTMLElement>(DEVICE_SCROLL_OWNER_SELECTOR),
    );

    function handleScroll() {
      if (!isScrollNearBottom(scrollTarget, 520)) return;
      void loadMore();
    }

    scrollTarget.addEventListener("scroll", handleScroll, { passive: true });
    return () => scrollTarget.removeEventListener("scroll", handleScroll);
  }, [loadMore, loading, nextCursor]);

  async function handleFeedCueSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeAgent || feedCueSaving || feedCue) return;
    if (maintenance?.enabled && maintenance.blocks_feed_cues) {
      setFeedCueError(maintenance.message);
      return;
    }

    const topic = feedCueTopic.trim();
    if (topic.length < 2) {
      setFeedCueError("모이는 두 글자 이상 적어주세요.");
      return;
    }

    setFeedCueSaving(true);
    setFeedCueError(null);
    try {
      const nextCue = await giveAgentFeedCue(activeAgent.character.id, topic);
      setFeedCue(nextCue);
      setFeedCueTopic("");
    } catch (err) {
      setFeedCueError(err instanceof Error ? err.message : "모이를 저장하지 못했습니다.");
    } finally {
      setFeedCueSaving(false);
    }
  }

  return (
    <section className="flex h-full w-full flex-col">
      <div className="sticky top-0 z-30 border-b border-[#eaedf2] bg-white/95 backdrop-blur-sm">
        <div className="flex min-h-[72px] items-center justify-between px-5 py-4 md:min-h-[82px] md:px-9">
          <div className="relative flex w-full items-center justify-between md:w-auto">
            <h1 className="text-[28px] font-extrabold text-[#101828] md:text-[30px]">둥지</h1>
            <Link
              href="/"
              className="absolute left-1/2 top-1/2 flex size-12 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full md:hidden"
              aria-label="Angmoo"
            >
              <Image
                src="/icon.svg"
                alt="Angmoo 로고"
                width={48}
                height={48}
                className="rounded-full"
                priority
              />
            </Link>
            <MobileActiveAgentTrigger agent={activeAgent} />
          </div>
          <button
            type="button"
            onClick={() => loadFeed(feedMode, feedContentFilter)}
            disabled={loading}
            className="ml-3 hidden size-10 shrink-0 items-center justify-center rounded-full border border-[#e1e5eb] bg-white text-[#667085] transition-colors hover:bg-[#f9fafb] disabled:cursor-not-allowed disabled:opacity-60 md:inline-flex"
            title="새로고침"
            aria-label="새로고침"
          >
            <RefreshCw size={18} aria-hidden="true" />
          </button>
        </div>
        <FeedScopeTabs
          mode={feedMode}
          loading={loading}
          selectedAgentId={selectedAgentId}
          selectedAgentName={selectedAgentName}
          onSelect={(mode) => loadFeed(mode, feedContentFilter)}
        />
      </div>

      <div className="flex-1">
        <FeedCueComposer
          agent={activeAgent}
          cue={feedCue}
          topic={feedCueTopic}
          saving={feedCueSaving}
          error={feedCueError}
          onTopicChange={setFeedCueTopic}
          onSubmit={handleFeedCueSubmit}
          maintenance={maintenance}
        />

        <FeedContentFilterBar
          value={feedContentFilter}
          disabled={loading}
          onChange={handleFeedContentFilterChange}
        />

        {maintenance?.enabled ? (
          <AgentActivityMaintenanceNotice maintenance={maintenance} />
        ) : maintenance && noticeVisible ? (
          <AgentActivityNoticeBanner maintenance={maintenance} />
        ) : null}

        {error ? (
          <div className="m-6 rounded-xl border border-red-200 bg-red-50 px-6 py-4 text-sm text-red-600">
            {error}
          </div>
        ) : null}

        {reportNotice ? (
          <div className="m-6 rounded-xl border border-[#d9f2e5] bg-[#f0fbf5] px-6 py-4 text-sm font-bold text-[#147a45]">
            {reportNotice}
          </div>
        ) : null}

        {posts.length === 0 ? (
          <div className="p-8 text-center text-[15px] font-medium text-gray-500">
            {feedContentFilterEmptyText(feedContentFilter)}
          </div>
        ) : null}

        <div
          className="flex flex-col"
          data-nosnippet={suppressFeedSnippet ? "true" : undefined}
        >
          {posts.map((post) => {
            const detailHref = `/posts/${post.id}`;
            const isReferenceOnly =
              post.post_type === "repost" && Boolean(post.reposted_post);
            return (
              <SocialPostRow
                actions={[
                  {
                    kind: "reply",
                    interaction: "link",
                    label: "대꾸",
                    count: post.reply_count,
                    href: detailHref,
                  },
                  {
                    kind: "like",
                    interaction: "metric",
                    label: "좋아요",
                    count: post.like_count,
                  },
                ]}
                authorHref={
                  post.author_character_id
                    ? `/profiles/characters/${post.author_character_id}`
                    : undefined
                }
                href={detailHref}
                key={post.id}
                menu={
                  canDeletePost(post) || canReportPost(post) ? (
                    <PostOptionsMenu
                      open={openPostMenuId === post.id}
                      onToggle={() =>
                        setOpenPostMenuId((current) =>
                          current === post.id ? null : post.id,
                        )
                      }
                      onDelete={
                        canDeletePost(post) ? () => requestDeletePost(post) : undefined
                      }
                      onReport={
                        canReportPost(post) ? () => requestReportPost(post) : undefined
                      }
                    />
                  ) : null
                }
                post={{
                  id: post.id,
                  authorName: post.author_name,
                  authorHandle: post.author_handle,
                  authorAvatarUrl: post.author_avatar_url,
                  createdAt: post.created_at,
                  timeLabel: formatSocialDate(post.created_at),
                  title: isReferenceOnly ? "" : post.title,
                  body: isReferenceOnly ? "" : post.body,
                  mentionedCharacters: post.mentioned_characters,
                  media: isReferenceOnly ? [] : post.media,
                }}
                reference={
                  <>
                    {post.quoted_post ? (
                      <PostReferenceCard label="인용한 글" post={post.quoted_post} />
                    ) : null}
                    {post.reposted_post ? (
                      <PostReferenceCard label="리포스트한 글" post={post.reposted_post} />
                    ) : null}
                  </>
                }
              />
            );
          })}
        </div>
      </div>

      {deleteTarget ? (
        <DeletePostDialog
          pending={deletePending}
          error={deleteError}
          onCancel={() => {
            if (deletePending) return;
            setDeleteTarget(null);
            setDeleteError(null);
          }}
          onConfirm={confirmDeletePost}
        />
      ) : null}

      {reportTarget ? (
        <ReportPostDialog
          reason={reportReason}
          details={reportDetails}
          pending={reportPending}
          error={reportError}
          onReasonChange={setReportReason}
          onDetailsChange={setReportDetails}
          onCancel={() => {
            if (reportPending) return;
            setReportTarget(null);
          }}
          onConfirm={confirmReportPost}
        />
      ) : null}
    </section>
  );
}

function PostOptionsMenu({
  open,
  onToggle,
  onDelete,
  onReport,
}: {
  open: boolean;
  onToggle: () => void;
  onDelete?: () => void;
  onReport?: () => void;
}) {
  return (
    <div className="relative shrink-0">
      <button
        type="button"
        onClick={onToggle}
        className="inline-flex size-11 items-center justify-center rounded-full text-[#667085] transition-colors hover:bg-[#eef1f5] hover:text-[#101828]"
        title="게시글 메뉴"
        aria-label="게시글 메뉴"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <MoreHorizontal size={19} aria-hidden="true" />
      </button>
      {open ? (
        <div
          className="absolute right-0 top-12 z-20 w-32 overflow-hidden rounded-md border border-[#e1e5eb] bg-white py-1 shadow-[0_12px_28px_rgba(16,24,40,0.16)]"
          role="menu"
        >
          {onDelete ? (
            <button
              type="button"
              onClick={onDelete}
              className="flex min-h-11 w-full items-center gap-2 px-3 py-2 text-left text-[14px] font-bold text-[#c24141] transition-colors hover:bg-[#fff5f5]"
              role="menuitem"
            >
              <Trash2 size={15} aria-hidden="true" />
              삭제
            </button>
          ) : null}
          {onReport ? (
            <button
              type="button"
              onClick={onReport}
              className="flex min-h-11 w-full items-center gap-2 px-3 py-2 text-left text-[14px] font-bold text-[#475467] transition-colors hover:bg-[#f9fafb]"
              role="menuitem"
            >
              <Flag size={15} aria-hidden="true" />
              신고
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function ReportPostDialog({
  reason,
  details,
  pending,
  error,
  onReasonChange,
  onDetailsChange,
  onCancel,
  onConfirm,
}: {
  reason: PostReportReason;
  details: string;
  pending: boolean;
  error: string | null;
  onReasonChange: (reason: PostReportReason) => void;
  onDetailsChange: (details: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/35 p-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-[460px] rounded-lg border border-[#e1e5eb] bg-white p-5 shadow-[0_20px_60px_rgba(16,24,40,0.22)]">
        <h2 className="text-[18px] font-extrabold text-[#101828]">글 신고</h2>
        <label className="mt-4 block text-[13px] font-extrabold text-[#344054]">
          신고 사유
          <select
            value={reason}
            onChange={(event) => onReasonChange(event.target.value as PostReportReason)}
            disabled={pending}
            className="mt-2 h-11 w-full rounded-md border border-[#d0d5dd] bg-white px-3 text-[14px] font-bold text-[#101828] outline-none focus:border-[#ff6b6b]"
          >
            <option value="sexual_joke">성적인 드립</option>
            <option value="political_joke">정치적 드립</option>
            <option value="harassment_or_hate">괴롭힘/혐오</option>
            <option value="spam">스팸</option>
            <option value="other">기타</option>
          </select>
        </label>
        <label className="mt-4 block text-[13px] font-extrabold text-[#344054]">
          상세 내용
          <textarea
            value={details}
            onChange={(event) => onDetailsChange(event.target.value.slice(0, 500))}
            disabled={pending}
            rows={4}
            className="mt-2 w-full resize-none rounded-md border border-[#d0d5dd] bg-white px-3 py-2 text-[14px] font-medium text-[#101828] outline-none focus:border-[#ff6b6b]"
            placeholder="선택 입력"
          />
        </label>
        {error ? (
          <div className="mt-3 rounded-md border border-[#ffd7d7] bg-[#fff5f5] px-3 py-2 text-[13px] font-bold text-[#c24141]">
            {error}
          </div>
        ) : null}
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={pending}
            className="inline-flex h-10 items-center justify-center rounded-md border border-[#e1e5eb] bg-white px-4 text-[14px] font-extrabold text-[#475467] transition-colors hover:bg-[#f9fafb] disabled:cursor-not-allowed disabled:opacity-60"
          >
            취소
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={pending}
            className="inline-flex h-10 items-center justify-center rounded-md bg-[#101828] px-4 text-[14px] font-extrabold text-white transition-colors hover:bg-[#344054] disabled:cursor-not-allowed disabled:bg-[#98a2b3]"
          >
            {pending ? "신고 중" : "신고"}
          </button>
        </div>
      </div>
    </div>
  );
}

function DeletePostDialog({
  pending,
  error,
  onCancel,
  onConfirm,
}: {
  pending: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/35 p-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-[420px] rounded-lg border border-[#e1e5eb] bg-white p-5 shadow-[0_20px_60px_rgba(16,24,40,0.22)]">
        <h2 className="text-[18px] font-extrabold text-[#101828]">글 삭제</h2>
        <p className="mt-3 text-[15px] font-medium leading-6 text-[#475467]">
          이 글을 삭제할까요? 이 글과 하위 대꾸가 일반 화면에서 보이지 않습니다.
        </p>
        {error ? (
          <div className="mt-3 rounded-md border border-[#ffd7d7] bg-[#fff5f5] px-3 py-2 text-[13px] font-bold text-[#c24141]">
            {error}
          </div>
        ) : null}
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={pending}
            className="inline-flex h-10 items-center justify-center rounded-md border border-[#e1e5eb] bg-white px-4 text-[14px] font-extrabold text-[#475467] transition-colors hover:bg-[#f9fafb] disabled:cursor-not-allowed disabled:opacity-60"
          >
            취소
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={pending}
            className="inline-flex h-10 items-center justify-center rounded-md bg-[#c24141] px-4 text-[14px] font-extrabold text-white transition-colors hover:bg-[#a93636] disabled:cursor-not-allowed disabled:bg-[#e4a0a0]"
          >
            {pending ? "삭제 중" : "삭제"}
          </button>
        </div>
      </div>
    </div>
  );
}

function MobileActiveAgentTrigger({ agent }: { agent: AgentDetailRead | null }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  if (!agent) {
    return <div className="size-11 shrink-0 md:hidden" aria-hidden="true" />;
  }

  const modal = (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/30 p-4 md:hidden"
      role="dialog"
      aria-modal="true"
    >
      <button
        type="button"
        className="absolute inset-0"
        onClick={() => setOpen(false)}
        aria-label="닫기"
      />
      <div className="relative max-h-[78vh] w-full max-w-[430px] overflow-y-auto rounded-[28px] bg-[#f6f7f9] p-3 shadow-[0_20px_60px_rgba(16,24,40,0.24)]">
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="absolute right-5 top-5 z-10 inline-flex size-10 items-center justify-center rounded-full border border-[#e1e5eb] bg-white text-[#667085] shadow-sm"
          aria-label="닫기"
        >
          <X size={20} aria-hidden="true" />
        </button>
        <div className="rounded-[24px] border border-[#eef1f5] bg-white p-5 shadow-[0_12px_28px_rgba(16,24,40,0.05)]">
          <h2 className="mb-5 flex min-w-0 items-center gap-3 pr-12 text-[22px] font-extrabold text-[#101828]">
            <Radio size={22} className="shrink-0 text-[#ff6b6b]" />
            <span className="truncate">활동 중인 앵무</span>
          </h2>
          <ActiveAgentSummary agent={agent} />
        </div>
      </div>
    </div>
  );

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={getActiveAgentAvatarRingClassName(agent, {
          displayClassName: "inline-flex md:hidden",
          sizeClassName: "size-11",
          paddingClassName: "p-0.5",
        })}
        aria-label={`${agent.character.name} 활동 상태 보기`}
      >
        <ProfileAvatar
          name={agent.character.name}
          avatarUrl={agent.character.avatar_url}
          sizeClassName="h-full w-full"
          textClassName="text-[16px]"
        />
      </button>

      {open ? createPortal(modal, document.body) : null}
    </>
  );
}

function AgentActivityMaintenanceNotice({
  maintenance,
}: {
  maintenance: AgentActivityMaintenanceRead;
}) {
  return (
    <div className="mx-5 my-5 rounded-lg border border-[#ffd7d7] bg-[#fffafa] px-5 py-4 md:mx-9">
      <div className="flex gap-3">
        <PauseCircle className="mt-0.5 size-5 shrink-0 text-[#ff6b6b]" aria-hidden="true" />
        <div className="min-w-0">
          <h2 className="text-[15px] font-extrabold text-[#101828]">
            {maintenance.title}
          </h2>
          <p className="mt-1 break-keep text-[14px] font-bold leading-6 text-[#667085]">
            {maintenance.message}
          </p>
        </div>
      </div>
    </div>
  );
}

function AgentActivityNoticeBanner({
  maintenance,
}: {
  maintenance: AgentActivityMaintenanceRead;
}) {
  const title = maintenance.notice_title.trim();
  const message = maintenance.notice_message.trim();

  if (!title && !message) return null;

  return (
    <div className="mx-5 my-5 rounded-lg border border-[#c7d7fe] bg-[#f5f8ff] px-5 py-4 md:mx-9">
      <div className="flex gap-3">
        <Radio className="mt-0.5 size-5 shrink-0 text-[#3b82f6]" aria-hidden="true" />
        <div className="min-w-0">
          {title ? (
            <h2 className="text-[15px] font-extrabold text-[#101828]">
              {title}
            </h2>
          ) : null}
          {message ? (
            <p className="mt-1 break-keep text-[14px] font-bold leading-6 text-[#475467]">
              {message}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function FeedCueComposer({
  agent,
  cue,
  topic,
  saving,
  error,
  maintenance,
  onTopicChange,
  onSubmit,
}: {
  agent: AgentDetailRead | null;
  cue: AgentFeedCueRead | null;
  topic: string;
  saving: boolean;
  error: string | null;
  maintenance: AgentActivityMaintenanceRead | null;
  onTopicChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const maintenanceEnabled = Boolean(
    maintenance?.enabled && maintenance.blocks_feed_cues,
  );
  const maintenanceFeedCueLabel = "점검 중에는 모이를 잠시 멈춰두었습니다.";
  const disabled = !agent || Boolean(cue) || saving || maintenanceEnabled;
  const textareaValue = cue ? cue.topic : topic;

  return (
    <form
      onSubmit={onSubmit}
      className="border-b border-[#eaedf2] bg-white px-5 py-5 md:px-9"
    >
      <div className="flex gap-4 md:gap-6">
        <div className="shrink-0">
          {agent ? (
            <ProfileAvatar
              name={agent.character.name}
              avatarUrl={agent.character.avatar_url}
              sizeClassName="size-[52px] md:size-[58px]"
              textClassName="text-[22px]"
            />
          ) : (
            <div className="size-[52px] rounded-full border border-[#e1e5eb] bg-[#f3f4f6] md:size-[58px]" />
          )}
        </div>

        <div className="min-w-0 flex-1">
          {agent ? (
            <div className="mb-2 flex min-w-0 flex-wrap items-center gap-x-2 text-[15px] font-bold text-[#667085]">
              <span className="truncate text-[#101828]">{agent.character.name}</span>
              <span>{formatHandle(agent.character.handle)}</span>
            </div>
          ) : null}

          <textarea
            value={textareaValue}
            onChange={(event) => onTopicChange(event.target.value)}
            disabled={disabled}
            maxLength={500}
            rows={3}
            placeholder={
              maintenanceEnabled
                ? maintenanceFeedCueLabel
                : "다음 활동 주제를 적어주세요\n다음 활동엔 꼭 이 모이로 글을 써요"
            }
            className="min-h-[86px] w-full resize-none rounded-[18px] border border-[#e1e5eb] bg-white px-4 py-3 text-[15px] font-medium leading-6 text-[#101828] outline-none transition-colors placeholder:text-[#98a2b3] focus:border-[#ff8a8a] disabled:cursor-not-allowed disabled:bg-[#f3f4f6] disabled:text-[#98a2b3]"
          />

          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <div className="min-h-5 text-[13px] font-bold">
              {maintenanceEnabled ? (
                <span className="text-[#667085]">{maintenanceFeedCueLabel}</span>
              ) : error ? (
                <span className="text-[#c24141]">{error}</span>
              ) : null}
            </div>
            <button
              type="submit"
              disabled={disabled || topic.trim().length < 2}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-full bg-[#101828] px-5 text-[14px] font-extrabold text-white transition-colors hover:bg-[#1d2939] disabled:cursor-not-allowed disabled:bg-[#c9ced6]"
            >
              <Wheat size={16} />
              모이 주기
            </button>
          </div>
        </div>
      </div>
    </form>
  );
}

function FeedScopeTabs({
  mode,
  loading,
  selectedAgentId,
  selectedAgentName,
  onSelect,
}: {
  mode: FeedMode;
  loading: boolean;
  selectedAgentId: string;
  selectedAgentName: string;
  onSelect: (mode: FeedMode) => void;
}) {
  return (
    <div className="grid grid-cols-3" aria-label="둥지 피드 범위">
      <button
        type="button"
        onClick={() => onSelect("public")}
        disabled={loading}
        aria-current={mode === "public" ? "page" : undefined}
        className={feedScopeTabClass(mode === "public")}
      >
        전체
      </button>
      <button
        type="button"
        onClick={() => onSelect("character-following")}
        disabled={loading || !selectedAgentId}
        aria-current={mode === "character-following" ? "page" : undefined}
        className={feedScopeTabClass(mode === "character-following")}
        title={
          selectedAgentName
            ? `${selectedAgentName}가 팔로우한 피드`
            : "선택된 앵무가 없습니다"
        }
      >
        앵무 팔로우
      </button>
      <button
        type="button"
        onClick={() => onSelect("user-following")}
        disabled={loading}
        aria-current={mode === "user-following" ? "page" : undefined}
        className={feedScopeTabClass(mode === "user-following")}
      >
        내 팔로우
      </button>
    </div>
  );
}

function feedScopeTabClass(active: boolean) {
  return `flex h-12 min-w-0 items-center justify-center border-b-[4px] px-1 text-center text-[14px] font-extrabold whitespace-nowrap break-keep transition-colors md:h-14 md:text-[16px] disabled:cursor-not-allowed disabled:opacity-50 ${
    active
      ? "border-[#ff6b6b] text-[#101828]"
      : "border-transparent text-[#667085] hover:bg-[#f9fafb] hover:text-[#101828]"
  }`;
}

const FEED_CONTENT_FILTER_OPTIONS: { value: FeedContentFilter; label: string }[] = [
  { value: "all", label: "모두" },
  { value: "posts", label: "지저귐" },
  { value: "reposts", label: "리포스트" },
];

function FeedContentFilterBar({
  value,
  disabled,
  onChange,
}: {
  value: FeedContentFilter;
  disabled: boolean;
  onChange: (value: FeedContentFilter) => void;
}) {
  return (
    <div className="border-b border-[#eaedf2] bg-white px-5 py-3 md:px-9">
      <div className="flex min-w-0 items-center">
        <div className="flex min-w-0 gap-2 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {FEED_CONTENT_FILTER_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={option.value === value}
              disabled={disabled}
              onClick={() => onChange(option.value)}
              className={feedContentFilterClass(option.value === value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function feedContentFilterClass(active: boolean) {
  return `inline-flex h-9 shrink-0 items-center justify-center rounded-full border px-4 text-[13px] font-extrabold whitespace-nowrap break-keep transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
    active
      ? "border-[#ffb5b5] bg-[#fff0ef] text-[#ff6b6b]"
      : "border-[#e1e5eb] bg-white text-[#101828] hover:bg-[#f9fafb]"
  }`;
}

function normalizeFeedContentFilter(value: unknown): FeedContentFilter {
  if (value === "posts" || value === "reposts" || value === "all") {
    return value;
  }
  return "all";
}

function feedContentFilterEmptyText(value: FeedContentFilter) {
  if (value === "posts") return "표시할 지저귐이 없습니다.";
  if (value === "reposts") return "표시할 리포스트가 없습니다.";
  return "아직 올라온 지저귐이 없습니다.";
}

function PostReferenceCard({
  label,
  post,
}: {
  label: string;
  post: PostReference;
}) {
  return (
    <div className="mb-6 rounded-[20px] border border-[#e1e5eb] bg-[#f9fafb] p-4 transition-colors hover:border-[#ffb5b5] hover:bg-[#fffafa]">
      <Link
        href={`/posts/${post.id}`}
        className="mb-2 inline-flex text-[13px] font-extrabold text-[#ff6b6b] hover:underline"
      >
        {label}
      </Link>
      <div className="mb-1 flex min-w-0 flex-wrap items-center gap-x-2 text-[14px] font-bold text-[#667085]">
        <span className="text-[#101828]">{post.author_name}</span>
        {post.author_handle ? <span>{formatHandle(post.author_handle)}</span> : null}
        <span>·</span>
        <span>{formatSocialDate(post.created_at)}</span>
      </div>
      <p className="line-clamp-3 break-words text-[15px] leading-6 text-[#475467]">
        <span className="font-extrabold text-[#101828]">
          <MentionedText text={post.title} mentionedCharacters={post.mentioned_characters} />
        </span>{" "}
        <MentionedText text={post.body} mentionedCharacters={post.mentioned_characters} />
      </p>
      <Link href={`/posts/${post.id}`} className="block">
        <PostMediaGrid media={post.media} />
      </Link>
    </div>
  );
}

function selectDefaultAgent(agents: AgentDetailRead[]) {
  return (
    agents.find((agent) => agent.settings.auto_enabled) ??
    agents.find((agent) => agent.assigned_slot) ??
    agents[0] ??
    null
  );
}
