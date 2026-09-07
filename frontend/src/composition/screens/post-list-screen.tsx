"use client";
import { AgentActivityMaintenanceNotice,AgentActivityNoticeBanner,FeedCueComposer,MobileActiveAgentTrigger,selectDefaultAgent } from "@/features/characters/components/feed-activity-parts";
import { DeletePostDialog,FeedContentFilterBar,feedContentFilterEmptyText,type FeedMode,FeedScopeTabs,mergeUniquePosts,normalizeFeedContentFilter,PostOptionsMenu,PostReferenceCard,ReportPostDialog } from "@/features/social/components/post-feed-parts";


import { useMobilePullToRefresh } from "@/hooks/use-mobile-pull-to-refresh";
import { AUTH_CHANGED_EVENT,getStoredUser,storeUser,type UserRead } from "@/lib/auth/browser-session";
import { isScrollNearBottom,resolveScrollEventTarget } from "@/lib/dom/scroll-viewport";
import {
RefreshCw
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import type { FormEvent } from "react";
import { useCallback,useEffect,useRef,useState } from "react";

import { getAgentActivityMaintenance,getAgentFeedCue,giveAgentFeedCue,listAgents } from "@/features/characters/api/feed-actor";
import { selectActiveAgent } from "@/features/characters/components/active-agent-summary";
import type { AgentActivityMaintenanceRead,AgentDetailRead,AgentFeedCueRead } from "@/features/characters/types/feed-actor";
import { deleteSocialPost,formatSocialDate,listCharacterFollowingSocialFeed,listFollowingSocialFeed,listSocialFeed,reportSocialPost } from "@/features/social/api/social-feed-client";
import { SocialPostRow } from "@/features/social/components/social-post-row";
import type { FeedContentFilter,FeedPage,PostReportReason,PostSummary } from "@/features/social/types/social-feed-contract";
const DEVICE_SCROLL_OWNER_SELECTOR = '[data-device-scroll-owner="true"]';

export function PostListClient({
  updateUserFeedPreferences,
  initialFeed,
  initialError,
  suppressFeedSnippet = false,
}: {
  updateUserFeedPreferences: (data: { feed_content_filter: FeedContentFilter }) => Promise<UserRead>;
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
    [feedContentFilter, feedMode, loadFeed, loading, updateUserFeedPreferences],
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
