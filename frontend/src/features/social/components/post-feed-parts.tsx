"use client";
import { MentionedText } from "@/components/content/mentioned-text";
import { PostMediaGrid } from "@/components/media/post-media-grid";
import { formatSocialDate } from "@/features/social/api/social-feed-client";
import type { FeedContentFilter,PostReference,PostReportReason,PostSummary } from "@/features/social/types/social-feed-contract";
import { formatHandle } from "@/utils/profile-presentation";
import {
Flag,
MoreHorizontal,
Trash2
} from "lucide-react";
import Link from "next/link";

export type FeedMode = "public" | "character-following" | "user-following";

export function mergeUniquePosts(
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

export function FeedScopeTabs({
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

export function feedScopeTabClass(active: boolean) {
  return `flex h-12 min-w-0 items-center justify-center border-b-[4px] px-1 text-center text-[14px] font-extrabold whitespace-nowrap break-keep transition-colors md:h-14 md:text-[16px] disabled:cursor-not-allowed disabled:opacity-50 ${
    active
      ? "border-[#ff6b6b] text-[#101828]"
      : "border-transparent text-[#667085] hover:bg-[#f9fafb] hover:text-[#101828]"
  }`;
}

export const FEED_CONTENT_FILTER_OPTIONS: { value: FeedContentFilter; label: string }[] = [
  { value: "all", label: "모두" },
  { value: "posts", label: "지저귐" },
  { value: "reposts", label: "리포스트" },
];

export function FeedContentFilterBar({
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

export function feedContentFilterClass(active: boolean) {
  return `inline-flex h-9 shrink-0 items-center justify-center rounded-full border px-4 text-[13px] font-extrabold whitespace-nowrap break-keep transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
    active
      ? "border-[#ffb5b5] bg-[#fff0ef] text-[#ff6b6b]"
      : "border-[#e1e5eb] bg-white text-[#101828] hover:bg-[#f9fafb]"
  }`;
}

export function normalizeFeedContentFilter(value: unknown): FeedContentFilter {
  if (value === "posts" || value === "reposts" || value === "all") {
    return value;
  }
  return "all";
}

export function feedContentFilterEmptyText(value: FeedContentFilter) {
  if (value === "posts") return "표시할 지저귐이 없습니다.";
  if (value === "reposts") return "표시할 리포스트가 없습니다.";
  return "아직 올라온 지저귐이 없습니다.";
}

export function PostReferenceCard({
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
