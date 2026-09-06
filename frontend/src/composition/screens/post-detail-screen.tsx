"use client";
import { aggregatePostActions,buildReplyTree,DeletePostDialog,type DeleteTarget,mapRepliesById,PostOptionsMenu,PostReferenceCard,ReplyNodeRow,ReportPostDialog,type ReportTarget } from "@/features/social/components/post-detail-parts";


import { useRuntimeRouter as useRouter } from "@/hooks/use-runtime-navigation";
import {
ArrowLeft,
RefreshCw
} from "lucide-react";
import Link from "next/link";
import { useEffect,useMemo,useState } from "react";

import { listAgents } from "@/features/characters/api/feed-actor";
import { deleteSocialPost,getSocialPostThread,reportSocialPost } from "@/features/social/api/social-feed-client";
import { SocialPostRow } from "@/features/social/components/social-post-row";
import { type PostDetail,type PostReportReason,type PostSummary,type PostThreadRead } from "@/features/social/types/social-feed-contract";
import { AUTH_CHANGED_EVENT,getStoredUser,type UserRead } from "@/lib/auth/browser-session";
import { formatDate } from "@/utils/profile-presentation";

const EMPTY_REPLIES: PostSummary[] = [];

export function PostDetailClient({
  postId,
  initialThread,
  initialError,
}: {
  postId: string;
  initialThread: PostThreadRead | null;
  initialError: string | null;
}) {
  const router = useRouter();
  const [thread, setThread] = useState<PostThreadRead | null>(initialThread);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(initialError);
  const [viewer, setViewer] = useState<UserRead | null>(null);
  const [ownedCharacterIds, setOwnedCharacterIds] = useState<string[]>([]);
  const [openPostMenuId, setOpenPostMenuId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const [deletePending, setDeletePending] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [reportTarget, setReportTarget] = useState<ReportTarget | null>(null);
  const [reportReason, setReportReason] = useState<PostReportReason>("other");
  const [reportDetails, setReportDetails] = useState("");
  const [reportPending, setReportPending] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const [reportNotice, setReportNotice] = useState<string | null>(null);

  const post = thread?.post ?? null;
  const replies = thread?.replies ?? EMPTY_REPLIES;
  const repliesById = useMemo(() => mapRepliesById(replies), [replies]);
  const replyTree = useMemo(
    () => buildReplyTree(replies, post?.id ?? postId),
    [post?.id, postId, replies],
  );

  async function loadThread() {
    setLoading(true);
    setError(null);

    try {
      setThread(await getSocialPostThread(postId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "게시글을 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const syncViewer = () => setViewer(getStoredUser());
    syncViewer();
    window.addEventListener(AUTH_CHANGED_EVENT, syncViewer);
    return () => window.removeEventListener(AUTH_CHANGED_EVENT, syncViewer);
  }, []);

  useEffect(() => {
    let active = true;
    listAgents()
      .then((agents) => {
        if (active) setOwnedCharacterIds(agents.map((agent) => agent.character.id));
      })
      .catch(() => {
        if (active) setOwnedCharacterIds([]);
      });
    return () => {
      active = false;
    };
  }, []);

  function canDeletePost(
    target: Pick<
      PostDetail | PostSummary,
      "author_user_id" | "author_character_id" | "report_hidden"
    >,
  ) {
    if (target.report_hidden) return false;
    if (target.author_character_id) {
      return ownedCharacterIds.includes(target.author_character_id);
    }
    return Boolean(viewer?.id && target.author_user_id === viewer.id);
  }

  function canReportPost(target: PostDetail | PostSummary) {
    return Boolean(viewer?.id && !target.report_hidden && !canDeletePost(target));
  }

  function requestDeletePost(target: PostDetail | PostSummary, root: boolean) {
    setDeleteTarget({ post: target, root });
    setDeleteError(null);
    setOpenPostMenuId(null);
  }

  function requestReportPost(target: PostDetail | PostSummary, root: boolean) {
    setReportTarget({ post: target, root });
    setReportReason("other");
    setReportDetails("");
    setReportError(null);
    setOpenPostMenuId(null);
  }

  async function confirmDeletePost() {
    if (!deleteTarget || deletePending) return;
    setDeletePending(true);
    setDeleteError(null);
    try {
      await deleteSocialPost(deleteTarget.post.id);
      if (deleteTarget.root) {
        router.push("/posts");
        return;
      }
      setDeleteTarget(null);
      await loadThread();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "글을 삭제하지 못했습니다.");
    } finally {
      setDeletePending(false);
    }
  }

  async function confirmReportPost() {
    if (!reportTarget || reportPending) return;
    setReportPending(true);
    setReportError(null);
    try {
      const result = await reportSocialPost(reportTarget.post.id, {
        reason: reportReason,
        details: reportDetails.trim() || undefined,
      });
      setReportTarget(null);
      setReportNotice(
        result.already_reported ? "이미 신고한 글입니다." : "신고가 접수되었습니다.",
      );
      if (result.report_hidden) {
        if (reportTarget.root) {
          await loadThread();
        } else {
          setThread((current) =>
            current
              ? {
                  ...current,
                  replies: current.replies.filter(
                    (reply) => reply.id !== reportTarget.post.id,
                  ),
                }
              : current,
          );
        }
      }
    } catch (err) {
      setReportError(err instanceof Error ? err.message : "신고를 접수하지 못했습니다.");
    } finally {
      setReportPending(false);
    }
  }

  return (
    <section className="min-h-screen bg-white">
      <div className="sticky top-0 z-30 flex min-h-[88px] items-center justify-between gap-3 border-b border-[#eaedf2] bg-white/95 px-5 py-4 backdrop-blur-sm md:px-9">
        <Link
          href="/posts"
          className="inline-flex size-11 items-center justify-center rounded-full border border-[#e1e5eb] bg-white text-[#667085] transition-colors hover:bg-[#f9fafb]"
          title="목록"
        >
          <ArrowLeft size={21} aria-hidden="true" />
        </Link>
        <h1 className="min-w-0 flex-1 truncate text-[28px] font-extrabold text-[#101828] md:text-[30px]">
          {post?.reply_to_post_id ? "대꾸" : "지저귐"}
        </h1>
        <button
          type="button"
          onClick={loadThread}
          disabled={loading}
          className="inline-flex size-11 items-center justify-center rounded-full border border-[#e1e5eb] bg-white text-[#667085] transition-colors hover:bg-[#f9fafb] disabled:cursor-not-allowed disabled:opacity-60"
          title="새로고침"
        >
          <RefreshCw size={20} aria-hidden="true" />
        </button>
      </div>

      {error ? (
        <div className="mx-5 mt-6 rounded-[24px] border border-[#ffd7d7] bg-[#fff5f5] px-5 py-4 text-[15px] font-medium text-[#c24141] md:mx-9">
          {error}
        </div>
      ) : null}

      {reportNotice ? (
        <div className="mx-5 mt-6 rounded-[24px] border border-[#d9f2e5] bg-[#f0fbf5] px-5 py-4 text-[15px] font-bold text-[#147a45] md:mx-9">
          {reportNotice}
        </div>
      ) : null}

      {loading ? (
        <div className="mx-5 mt-6 rounded-[24px] border border-[#eef1f5] bg-white px-6 py-8 text-[16px] font-medium text-[#667085] md:mx-9">
          게시글을 불러오는 중
        </div>
      ) : null}

      {post ? (
        <>
          {post.reply_to_post_id ? (
            <div className="border-b border-[#eaedf2] bg-white px-5 py-4 md:px-9">
              <Link
                href={`/posts/${post.reply_to_post_id}`}
                className="inline-flex rounded-full bg-[#fff0ef] px-4 py-2 text-[15px] font-extrabold text-[#ff6b6b] transition-colors hover:bg-[#ffe2e2]"
              >
                원글 보기
              </Link>
            </div>
          ) : null}

          <SocialPostRow
            actions={aggregatePostActions(post.id, post.reply_count, post.like_count)}
            authorHref={
              post.author_character_id
                ? `/profiles/characters/${post.author_character_id}`
                : undefined
            }
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
                    canDeletePost(post)
                      ? () => requestDeletePost(post, true)
                      : undefined
                  }
                  onReport={
                    canReportPost(post)
                      ? () => requestReportPost(post, true)
                      : undefined
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
              timeLabel: formatDate(post.created_at),
              title:
                post.post_type === "repost" && post.reposted_post
                  ? ""
                  : post.title,
              body:
                post.post_type === "repost" && post.reposted_post
                  ? ""
                  : post.body,
              mentionedCharacters: post.mentioned_characters,
              media:
                post.post_type === "repost" && post.reposted_post
                  ? []
                  : post.media,
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
            variant="detail"
          />

          <section className="bg-white">
            <h2 className="border-b border-[#eaedf2] px-5 py-5 text-[24px] font-extrabold text-[#101828] md:px-9">
              대꾸 {post.reply_count}
            </h2>
            {replyTree.map((node) => (
              <ReplyNodeRow
                key={node.reply.id}
                node={node}
                repliesById={repliesById}
                rootPostId={post.id}
                openPostMenuId={openPostMenuId}
                canDeletePost={canDeletePost}
                onToggleMenu={(replyId) =>
                  setOpenPostMenuId((current) => current === replyId ? null : replyId)
                }
                onDeletePost={(reply) => requestDeletePost(reply, false)}
                canReportPost={canReportPost}
                onReportPost={(reply) => requestReportPost(reply, false)}
              />
            ))}
          </section>
        </>
      ) : null}

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
