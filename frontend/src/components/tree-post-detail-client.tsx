"use client";

import { ArrowLeft, MessageCircle, RefreshCw, Send } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import type { FormEvent } from "react";

import { ProfileAvatar } from "@/components/profile-avatar";
import { hasStoredAuth } from "@/lib/agents";
import { formatDate } from "@/lib/community";
import { isOfficialOperatorName } from "@/lib/profile";
import {
  createTreeComment,
  getTreePost,
  type TreePostDetail,
} from "@/lib/tree";

export function TreePostDetailClient({
  postId,
  initialPost,
  initialError,
}: {
  postId: string;
  initialPost: TreePostDetail | null;
  initialError: string | null;
}) {
  const [post, setPost] = useState<TreePostDetail | null>(initialPost);
  const [loading, setLoading] = useState(false);
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(initialError);
  const [commentError, setCommentError] = useState<string | null>(null);

  async function loadPost() {
    setLoading(true);
    setError(null);
    try {
      setPost(await getTreePost(postId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "나무 글을 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  async function handleCommentSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = comment.trim();
    if (!hasStoredAuth()) {
      setCommentError("로그인 후 댓글을 쓸 수 있습니다.");
      return;
    }
    if (content.length < 2) {
      setCommentError("두 글자 이상 적어주세요.");
      return;
    }
    setSaving(true);
    setCommentError(null);
    try {
      setPost(await createTreeComment(postId, content));
      setComment("");
    } catch (err) {
      setCommentError(err instanceof Error ? err.message : "댓글을 저장하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="min-h-screen bg-white">
      <div className="sticky top-0 z-10 flex min-h-[88px] items-center justify-between gap-3 border-b border-[#eaedf2] bg-white/95 px-5 py-4 backdrop-blur-sm md:px-9">
        <Link
          href={`/tree?tab=${post?.category ?? "notice"}`}
          className="inline-flex size-11 items-center justify-center rounded-full border border-[#e1e5eb] bg-white text-[#667085] transition-colors hover:bg-[#f9fafb]"
          title="나무"
        >
          <ArrowLeft size={21} aria-hidden="true" />
        </Link>
        <h1 className="min-w-0 flex-1 truncate text-[28px] font-extrabold text-[#101828] md:text-[30px]">
          나무
        </h1>
        <button
          type="button"
          onClick={loadPost}
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

      {post ? (
        <>
          <article className="border-b border-[#eaedf2] bg-white px-5 py-8 md:px-9">
            <div className="flex gap-3 md:gap-6">
              <Link
                href={`/profiles/users/${post.author.id}`}
                className="shrink-0 rounded-full"
                aria-label={`${post.author.display_name} profile`}
              >
                <ProfileAvatar
                  name={post.author.display_name}
                  avatarUrl={post.author.avatar_url}
                  sizeClassName="size-12 md:size-[66px]"
                  textClassName="text-[18px] md:text-[28px]"
                />
              </Link>
              <div className="min-w-0 flex-1">
                <div className="mb-2 flex flex-wrap items-center gap-x-2 text-[18px] md:text-[22px]">
                  <span className="rounded-full bg-[#fff0ef] px-3 py-1 text-[13px] font-extrabold text-[#ff6b6b]">
                    {categoryLabel(post.category)}
                  </span>
                  <Link
                    href={`/profiles/users/${post.author.id}`}
                    className={treeAuthorNameClass(post.author.display_name)}
                  >
                    {post.author.display_name}
                  </Link>
                  <span className="font-medium text-[#667085]">·</span>
                  <span className="font-medium text-[#667085]">
                    {formatDate(post.created_at)}
                  </span>
                </div>
                {post.related_character ? (
                  <div className="mb-3 text-[14px] font-bold text-[#98a2b3]">
                    관련 앵무: {post.related_character.name}
                  </div>
                ) : null}
                <p className="whitespace-pre-wrap break-all text-[18px] leading-[1.55] text-[#101828] md:break-words md:text-[23px] md:leading-[1.5]">
                  <span className="font-bold">{post.title}</span>
                  {post.body === post.title ? "" : ` ${post.body}`}
                </p>
                <div className="mt-7 flex items-center gap-2 text-[#667085]">
                  <MessageCircle className="size-[24px]" strokeWidth={1.6} />
                  <span className="text-[17px] font-bold">{post.comments.length}</span>
                </div>
              </div>
            </div>
          </article>

          <form onSubmit={handleCommentSubmit} className="border-b border-[#eaedf2] px-5 py-5 md:px-9">
            <textarea
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              disabled={saving}
              rows={3}
              maxLength={1000}
              placeholder="댓글을 남겨주세요"
              className="min-h-[86px] w-full resize-none rounded-[18px] border border-[#e1e5eb] bg-white px-4 py-3 text-[15px] font-medium leading-6 text-[#101828] outline-none transition-colors placeholder:text-[#98a2b3] focus:border-[#ff8a8a] disabled:cursor-not-allowed disabled:bg-[#f3f4f6]"
            />
            <div className="mt-3 flex items-center justify-between gap-3">
              <div className="min-h-5 text-[13px] font-bold text-[#c24141]">
                {commentError}
              </div>
              <button
                type="submit"
                disabled={saving || comment.trim().length < 2}
                className="inline-flex h-10 items-center justify-center gap-2 rounded-full bg-[#101828] px-5 text-[14px] font-extrabold text-white transition-colors hover:bg-[#1d2939] disabled:cursor-not-allowed disabled:bg-[#c9ced6]"
              >
                <Send size={16} />
                {saving ? "저장 중" : "댓글 쓰기"}
              </button>
            </div>
          </form>

          <section>
            <h2 className="border-b border-[#eaedf2] px-5 py-5 text-[24px] font-extrabold text-[#101828] md:px-9">
              댓글 {post.comments.length}
            </h2>
            {post.comments.length === 0 ? (
              <div className="px-5 py-8 text-[15px] font-medium text-[#667085] md:px-9">
                아직 댓글이 없습니다.
              </div>
            ) : null}
            {post.comments.map((item) => (
              <article key={item.id} className="border-b border-[#eaedf2] px-5 py-5 md:px-9">
                <div className="flex gap-3 md:gap-4">
                  <Link
                    href={`/profiles/users/${item.author.id}`}
                    className="shrink-0 rounded-full"
                    aria-label={`${item.author.display_name} profile`}
                  >
                    <ProfileAvatar
                      name={item.author.display_name}
                      avatarUrl={item.author.avatar_url}
                      sizeClassName="size-10 md:size-[44px]"
                      textClassName="text-[15px] md:text-[18px]"
                    />
                  </Link>
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex flex-wrap items-center gap-2 text-[15px]">
                      <Link
                        href={`/profiles/users/${item.author.id}`}
                        className={treeAuthorNameClass(item.author.display_name)}
                      >
                        {item.author.display_name}
                      </Link>
                      <span className="font-medium text-[#667085]">
                        {formatDate(item.created_at)}
                      </span>
                    </div>
                    <p className="whitespace-pre-wrap break-words text-[16px] leading-7 text-[#475467]">
                      {item.content}
                    </p>
                  </div>
                </div>
              </article>
            ))}
          </section>
        </>
      ) : null}
    </section>
  );
}

function categoryLabel(category: string) {
  const labels: Record<string, string> = {
    notice: "공지",
    bug: "버그",
    suggestion: "제안",
    question: "질문",
    free: "잡담",
  };
  return labels[category] ?? category;
}

function treeAuthorNameClass(name: string) {
  return `font-extrabold hover:underline ${isOfficialOperatorName(name) ? "text-[#ff6b6b]" : "text-[#101828]"}`;
}
