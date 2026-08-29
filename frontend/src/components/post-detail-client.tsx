"use client";

import {
  ArrowLeft,
  Flag,
  Heart,
  MessageCircle,
  MoreHorizontal,
  RefreshCw,
  Share,
  Repeat2,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useRuntimeRouter as useRouter } from "@/shared/navigation/public";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { MentionedText } from "@/components/mentioned-text";
import { LocalProductLink } from "@/features/device-shell/public";
import { PostMediaGrid } from "@/components/post-media-grid";
import { ProfileAvatar } from "@/components/profile-avatar";
import {
  deletePost,
  formatDate,
  getPostThread,
  reportPost,
  type PostDetail,
  type PostReportReason,
  type PostReference,
  type PostSummary,
  type PostThreadRead,
} from "@/lib/community";
import {
  AUTH_CHANGED_EVENT,
  getStoredUser,
  listAgents,
  type UserRead,
} from "@/lib/agents";
import { formatHandle } from "@/lib/profile";

const EMPTY_REPLIES: PostSummary[] = [];

type DeleteTarget = {
  post: PostDetail | PostSummary;
  root: boolean;
};

type ReportTarget = {
  post: PostDetail | PostSummary;
  root: boolean;
};

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
      setThread(await getPostThread(postId));
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
      await deletePost(deleteTarget.post.id);
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
      const result = await reportPost(reportTarget.post.id, {
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

          <article className="border-b border-[#eaedf2] bg-white px-4 py-8 md:px-9">
            <div className="flex gap-3 md:gap-6">
              <LocalProductLink
                href={post.author_character_id ? `/profiles/characters/${post.author_character_id}` : `/posts/${post.id}`}
                className="shrink-0 pt-1"
              >
                <ProfileAvatar
                  name={post.author_name}
                  avatarUrl={post.author_avatar_url}
                  sizeClassName="size-12 md:size-[66px]"
                  textClassName="text-[18px] md:text-[28px]"
                />
              </LocalProductLink>
              <div className="relative min-w-0 flex-1 overflow-visible">
                <div
                  className={`mb-2 flex min-w-0 flex-wrap items-center gap-x-2 text-[18px] md:text-[23px] ${
                    canDeletePost(post) || canReportPost(post) ? "pr-11" : ""
                  }`}
                >
                  <span className="font-extrabold text-[#101828]">{post.author_name}</span>
                  {post.author_handle ? (
                    <span className="font-medium text-[#667085]">
                      {formatHandle(post.author_handle)}
                    </span>
                  ) : null}
                  <span className="font-medium text-[#667085]">·</span>
                  <span className="font-medium text-[#667085]">{formatDate(post.created_at)}</span>
                </div>
                {canDeletePost(post) || canReportPost(post) ? (
                  <div className="absolute right-0 top-0 z-10">
                    <PostOptionsMenu
                      open={openPostMenuId === post.id}
                      onToggle={() =>
                        setOpenPostMenuId((current) => current === post.id ? null : post.id)
                      }
                      onDelete={canDeletePost(post) ? () => requestDeletePost(post, true) : undefined}
                      onReport={canReportPost(post) ? () => requestReportPost(post, true) : undefined}
                    />
                  </div>
                ) : null}
                {post.post_type === "repost" && post.reposted_post ? null : (
                  <div>
                    <p className="whitespace-pre-wrap break-all text-[18px] leading-[1.55] text-[#101828] md:break-words md:text-[23px] md:leading-[1.5]">
                      <span className="font-bold">
                        <MentionedText text={post.title} mentionedCharacters={post.mentioned_characters} />
                      </span>{" "}
                      <MentionedText text={post.body} mentionedCharacters={post.mentioned_characters} />
                    </p>
                    <PostMediaGrid media={post.media} />
                  </div>
                )}
                {post.quoted_post ? (
                  <PostReferenceCard label="인용한 글" post={post.quoted_post} />
                ) : null}
                {post.reposted_post ? (
                  <PostReferenceCard label="리포스트한 글" post={post.reposted_post} />
                ) : null}
                <div className="mt-7 flex max-w-[560px] items-center justify-between text-[#667085]">
                  <Action icon={<MessageCircle className="size-[22px] md:size-[27px]" strokeWidth={1.6} />} value={post.reply_count} />
                  <Action icon={<Repeat2 className="size-[22px] md:size-[27px]" strokeWidth={1.6} />} value={post.repost_count} />
                  <Action
                    icon={
                      <Heart
                        className="size-[22px] md:size-[27px]"
                        strokeWidth={1.6}
                        fill={post.like_count > 0 ? "currentColor" : "none"}
                      />
                    }
                    value={post.like_count}
                    accent={post.like_count > 0}
                  />
                  <Action icon={<Share className="size-[22px] md:size-[27px]" strokeWidth={1.6} />} value={post.quote_count} />
                </div>
              </div>
            </div>
          </article>

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

type ReplyNode = {
  reply: PostSummary;
  children: ReplyNode[];
};

function ReplyNodeRow({
  node,
  repliesById,
  rootPostId,
  openPostMenuId,
  canDeletePost,
  canReportPost,
  onToggleMenu,
  onDeletePost,
  onReportPost,
  depth = 0,
}: {
  node: ReplyNode;
  repliesById: Map<string, PostSummary>;
  rootPostId: string;
  openPostMenuId: string | null;
  canDeletePost: (
    post: Pick<PostSummary, "author_user_id" | "author_character_id" | "report_hidden">,
  ) => boolean;
  canReportPost: (post: PostSummary) => boolean;
  onToggleMenu: (postId: string) => void;
  onDeletePost: (post: PostSummary) => void;
  onReportPost: (post: PostSummary) => void;
  depth?: number;
}) {
  const reply = node.reply;
  const parent =
    reply.reply_to_post_id && reply.reply_to_post_id !== rootPostId
      ? repliesById.get(reply.reply_to_post_id)
      : null;

  const isTopLevelReply = depth === 0;
  const hasMenu = canDeletePost(reply) || canReportPost(reply);

  return (
    <div className={isTopLevelReply ? "relative border-b border-[#eaedf2]" : "relative mt-3"}>
      <Link
        href={`/posts/${reply.id}`}
        className={`block transition-colors hover:bg-[#f9fafb] ${
          isTopLevelReply
            ? "px-4 py-5 md:px-9 md:py-6"
            : "rounded-[18px] px-3 py-3 md:px-4 md:py-4"
        }`}
      >
        <article className="flex gap-3 md:gap-5">
          <div className="shrink-0 pt-1">
            <ProfileAvatar
              name={reply.author_name}
              avatarUrl={reply.author_avatar_url}
              sizeClassName={isTopLevelReply ? "size-11 md:size-[48px]" : "size-8 md:size-[40px]"}
              textClassName={isTopLevelReply ? "text-[17px] md:text-[20px]" : "text-[13px] md:text-[17px]"}
            />
          </div>
          <div className="min-w-0 flex-1">
            <div className={`mb-2 flex min-w-0 flex-wrap items-center gap-2 text-[15px] ${hasMenu ? "pr-11" : ""}`}>
              <span className="max-w-full break-words rounded-full bg-[#fff0ef] px-3 py-1 font-extrabold text-[#ff6b6b]">
                {reply.author_name}
              </span>
              {reply.author_handle ? (
                <span className="min-w-0 break-words font-medium text-[#667085]">
                  {formatHandle(reply.author_handle)}
                </span>
              ) : null}
              <span className="shrink-0 font-medium text-[#667085]">{formatDate(reply.created_at)}</span>
            </div>
            {parent ? (
              <div className="mb-1 text-[13px] font-bold text-[#98a2b3]">
                {parent.author_name}에게 대꾸
              </div>
            ) : null}
            <p className="min-w-0 whitespace-pre-wrap break-words text-[17px] leading-7 text-[#475467]">
              {reply.post_type !== "reply" && reply.title ? (
                <span className="font-bold text-[#101828]">
                  <MentionedText text={reply.title} mentionedCharacters={reply.mentioned_characters} />{" "}
                </span>
              ) : null}
              <MentionedText text={reply.body} mentionedCharacters={reply.mentioned_characters} />
            </p>
            <div className="mt-4 flex w-full max-w-[360px] items-center justify-between text-[#667085]">
              <ReplyAction
                icon={<MessageCircle size={18} strokeWidth={1.7} aria-hidden="true" />}
                value={reply.reply_count}
              />
              <ReplyAction
                icon={<Repeat2 size={18} strokeWidth={1.7} aria-hidden="true" />}
                value={reply.repost_count}
              />
              <ReplyAction
                icon={
                  <Heart
                    size={18}
                    strokeWidth={1.7}
                    fill={reply.like_count > 0 ? "currentColor" : "none"}
                    aria-hidden="true"
                  />
                }
                value={reply.like_count}
                accent={reply.like_count > 0}
              />
              <ReplyAction
                icon={<Share size={18} strokeWidth={1.7} aria-hidden="true" />}
                value={reply.quote_count}
              />
            </div>
          </div>
        </article>
      </Link>
      {hasMenu ? (
        <div className={isTopLevelReply ? "absolute right-4 top-5 z-10 md:right-9 md:top-6" : "absolute right-2 top-2 z-10"}>
          <PostOptionsMenu
            open={openPostMenuId === reply.id}
            onToggle={() => onToggleMenu(reply.id)}
            onDelete={canDeletePost(reply) ? () => onDeletePost(reply) : undefined}
            onReport={canReportPost(reply) ? () => onReportPost(reply) : undefined}
          />
        </div>
      ) : null}
      {node.children.length > 0 ? (
        <div className={isTopLevelReply ? "mx-4 border-l border-[#d9dee8] pb-5 pl-3 md:mx-9 md:pl-5" : "pb-1"}>
          {node.children.map((child) => (
            <ReplyNodeRow
              key={child.reply.id}
              node={child}
              repliesById={repliesById}
              rootPostId={rootPostId}
              openPostMenuId={openPostMenuId}
              canDeletePost={canDeletePost}
              canReportPost={canReportPost}
              onToggleMenu={onToggleMenu}
              onDeletePost={onDeletePost}
              onReportPost={onReportPost}
              depth={depth + 1}
            />
          ))}
        </div>
      ) : null}
    </div>
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
        className="inline-flex size-9 items-center justify-center rounded-full bg-white/80 text-[#667085] transition-colors hover:bg-[#eef1f5] hover:text-[#101828]"
        title="게시글 메뉴"
        aria-label="게시글 메뉴"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <MoreHorizontal size={19} aria-hidden="true" />
      </button>
      {open ? (
        <div
          className="absolute right-0 top-10 z-20 w-32 overflow-hidden rounded-md border border-[#e1e5eb] bg-white py-1 shadow-[0_12px_28px_rgba(16,24,40,0.16)]"
          role="menu"
        >
          {onDelete ? (
            <button
              type="button"
              onClick={onDelete}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-[14px] font-bold text-[#c24141] transition-colors hover:bg-[#fff5f5]"
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
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-[14px] font-bold text-[#475467] transition-colors hover:bg-[#f9fafb]"
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

function ReplyAction({
  icon,
  value,
  accent = false,
}: {
  icon: ReactNode;
  value: number;
  accent?: boolean;
}) {
  return (
    <span
      className={`inline-flex min-w-10 items-center gap-2 text-[14px] font-medium ${
        accent ? "text-[#ff6b6b]" : "text-[#667085]"
      }`}
    >
      {icon}
      {value}
    </span>
  );
}

function mapRepliesById(replies: PostSummary[]) {
  return new Map(replies.map((reply) => [reply.id, reply]));
}

function buildReplyTree(replies: PostSummary[], rootPostId: string): ReplyNode[] {
  const nodes = new Map<string, ReplyNode>();
  const roots: ReplyNode[] = [];

  for (const reply of replies) {
    nodes.set(reply.id, { reply, children: [] });
  }

  for (const reply of replies) {
    const node = nodes.get(reply.id);
    if (!node) continue;

    const parentId = reply.reply_to_post_id;
    const parent = parentId && parentId !== rootPostId ? nodes.get(parentId) : null;
    if (parent) {
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  }

  return roots;
}

function Action({
  icon,
  value,
  accent = false,
}: {
  icon: ReactNode;
  value?: number;
  accent?: boolean;
}) {
  return (
    <span className={`flex items-center gap-2 ${accent ? "text-[#ff6b6b]" : ""}`}>
      <span className="rounded-full p-1.5">
        {icon}
      </span>
      {typeof value === "number" ? (
        <span className="text-[16px] font-medium md:text-[20px]">{value}</span>
      ) : null}
    </span>
  );
}

function PostReferenceCard({
  label,
  post,
}: {
  label: string;
  post: PostReference;
}) {
  return (
    <div className="mt-6 rounded-[20px] border border-[#e1e5eb] bg-[#f9fafb] p-4 transition-colors hover:border-[#ffb5b5] hover:bg-[#fffafa]">
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
        <span>{formatDate(post.created_at)}</span>
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
