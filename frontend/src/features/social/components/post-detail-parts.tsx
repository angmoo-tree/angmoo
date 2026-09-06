"use client";
import { MentionedText } from "@/components/content/mentioned-text";
import { PostMediaGrid } from "@/components/media/post-media-grid";
import { SocialPostRow } from "@/features/social/components/social-post-row";
import { type PostDetail,type PostReference,type PostReportReason,type PostSummary } from "@/features/social/types/social-feed-contract";
import { type SocialPostActionPresentation } from "@/features/social/types/social-presentation-contract";
import { formatDate,formatHandle } from "@/utils/profile-presentation";
import {
Flag,
MoreHorizontal,
Trash2
} from "lucide-react";
import Link from "next/link";

export function aggregatePostActions(
  postId: string,
  replyCount: number,
  likeCount: number,
): SocialPostActionPresentation[] {
  return [
    {
      kind: "reply",
      interaction: "link",
      label: "대꾸",
      count: replyCount,
      href: `/posts/${postId}`,
    },
    {
      kind: "like",
      interaction: "metric",
      label: "좋아요",
      count: likeCount,
    },
  ];
}

export type DeleteTarget = {
  post: PostDetail | PostSummary;
  root: boolean;
};

export type ReportTarget = {
  post: PostDetail | PostSummary;
  root: boolean;
};

export type ReplyNode = {
  reply: PostSummary;
  children: ReplyNode[];
};

export function ReplyNodeRow({
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
    <div
      className={
        isTopLevelReply
          ? "relative"
          : "relative ml-4 border-l border-[var(--color-border-control)] md:ml-8"
      }
    >
      <SocialPostRow
        actions={aggregatePostActions(
          reply.id,
          reply.reply_count,
          reply.like_count,
        )}
        authorHref={
          reply.author_character_id
            ? `/profiles/characters/${reply.author_character_id}`
            : undefined
        }
        context={parent ? `${parent.author_name}에게 대꾸` : undefined}
        href={`/posts/${reply.id}`}
        menu={
          hasMenu ? (
            <PostOptionsMenu
              open={openPostMenuId === reply.id}
              onToggle={() => onToggleMenu(reply.id)}
              onDelete={canDeletePost(reply) ? () => onDeletePost(reply) : undefined}
              onReport={canReportPost(reply) ? () => onReportPost(reply) : undefined}
            />
          ) : null
        }
        post={{
          id: reply.id,
          authorName: reply.author_name,
          authorHandle: reply.author_handle,
          authorAvatarUrl: reply.author_avatar_url,
          createdAt: reply.created_at,
          timeLabel: formatDate(reply.created_at),
          title: reply.post_type === "reply" ? "" : reply.title,
          body: reply.body,
          mentionedCharacters: reply.mentioned_characters,
          media: reply.media,
        }}
        variant="reply"
      />
      {node.children.length > 0 ? (
        <div>
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

export function PostOptionsMenu({
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
        className="inline-flex size-11 items-center justify-center rounded-full bg-white/80 text-[#667085] transition-colors hover:bg-[#eef1f5] hover:text-[#101828]"
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

export function ReportPostDialog({
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

export function DeletePostDialog({
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

export function mapRepliesById(replies: PostSummary[]) {
  return new Map(replies.map((reply) => [reply.id, reply]));
}

export function buildReplyTree(replies: PostSummary[], rootPostId: string): ReplyNode[] {
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

export function PostReferenceCard({
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
