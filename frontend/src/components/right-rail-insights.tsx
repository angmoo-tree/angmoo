"use client";

import { Flame, Heart, MessageCircle, Repeat2, Trophy } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { PostMediaGrid } from "@/components/post-media-grid";
import { ProfileAvatar } from "@/components/profile-avatar";
import { MentionedText } from "@/components/mentioned-text";
import {
  formatDate,
  listTodayActivity,
  listTodayPopularPosts,
  type PostSummary,
  type TodayActivityRead,
} from "@/lib/community";
import { formatHandle } from "@/lib/profile";

export function RightRailInsights() {
  const { posts, activities, loading, error } = useRightRailInsights();

  return (
    <>
      <PopularPostsCard posts={posts} loading={loading} error={error} />
      <TodayActivityCard activities={activities} loading={loading} error={error} />
    </>
  );
}

export function useRightRailInsights() {
  const [posts, setPosts] = useState<PostSummary[]>([]);
  const [activities, setActivities] = useState<TodayActivityRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    Promise.all([listTodayPopularPosts(10), listTodayActivity(50)])
      .then(([nextPosts, nextActivities]) => {
        if (!active) return;
        setPosts(nextPosts);
        setActivities(nextActivities);
        setError(null);
      })
      .catch((err) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : "오른쪽 패널을 불러오지 못했습니다.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  return { posts, activities, loading, error };
}

export function PopularPostsCard({
  posts,
  loading,
  error,
}: {
  posts: PostSummary[];
  loading: boolean;
  error: string | null;
}) {
  return (
    <section className="w-full rounded-[24px] border border-[#eef1f5] bg-white p-5 shadow-[0_12px_28px_rgba(16,24,40,0.05)]">
      <h3 className="mb-5 flex items-center gap-3 text-[22px] font-extrabold text-[#101828]">
        <Flame size={22} className="text-[#ff6b6b]" />
        반응 좋은 지저귐
      </h3>
      <p className="mb-5 -mt-3 text-[13px] font-bold text-[#667085]">서버 전체 · 오늘 기준</p>

      <RailState loading={loading} error={error} empty={!posts.length} emptyText="아직 반응이 모인 지저귐이 없습니다." />

      {!loading && !error && posts.length ? (
        <div className="flex max-h-[360px] flex-col gap-5 overflow-y-auto pr-1">
          {posts.map((post, index) => (
            <article
              key={post.id}
              className="rounded-[18px] border border-[#eef1f5] bg-[#f9fafb] p-4 transition-colors hover:border-[#ffb5b5] hover:bg-[#fffafa]"
            >
              <Link href={`/posts/${post.id}`} className="mb-3 flex items-center gap-3">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-white text-[15px] font-extrabold text-[#ff6b6b] shadow-sm">
                  {index + 1}
                </span>
                <ProfileAvatar
                  name={post.author_name}
                  avatarUrl={post.author_avatar_url}
                  sizeClassName="size-[38px]"
                  textClassName="text-[16px]"
                />
                <div className="min-w-0">
                  <div className="truncate text-[16px] font-extrabold text-[#101828]">
                    {post.author_name}
                  </div>
                  <div className="truncate text-[13px] font-bold text-[#667085]">
                    {post.author_handle ? formatHandle(post.author_handle) : formatDate(post.created_at)}
                  </div>
                </div>
              </Link>
              <p className="line-clamp-3 break-words text-[15px] leading-6 text-[#101828]">
                <span className="font-extrabold">
                  <MentionedText text={post.title} mentionedCharacters={post.mentioned_characters} />
                </span>{" "}
                <MentionedText text={post.body} mentionedCharacters={post.mentioned_characters} />
              </p>
              <Link href={`/posts/${post.id}`} className="block">
                <PostMediaGrid media={post.media} />
              </Link>
              <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 text-[13px] font-extrabold text-[#667085]">
                <span className="inline-flex items-center gap-1.5">
                  <MessageCircle size={15} />
                  {post.reply_count}
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <Repeat2 size={15} />
                  {post.repost_count}
                </span>
                <span className="inline-flex items-center gap-1.5 text-[#ff6b6b]">
                  <Heart size={15} fill="currentColor" />
                  {post.like_count}
                </span>
                <span>{getReactionScore(post)}점</span>
              </div>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}

export function TodayActivityCard({
  activities,
  loading,
  error,
}: {
  activities: TodayActivityRead[];
  loading: boolean;
  error: string | null;
}) {
  return (
    <section className="w-full rounded-[24px] border border-[#eef1f5] bg-white p-5 shadow-[0_12px_28px_rgba(16,24,40,0.05)]">
      <h3 className="mb-2 flex items-center gap-3 text-[22px] font-extrabold text-[#101828]">
        <Trophy size={22} className="text-[#ff6b6b]" />
        오늘의 활약
      </h3>
      <p className="mb-5 text-[13px] font-bold text-[#667085]">서버 전체 · 오늘 기준</p>

      <RailState loading={loading} error={error} empty={!activities.length} emptyText="오늘 집계할 앵무 활동이 아직 없습니다." />

      {!loading && !error && activities.length ? (
        <div className="flex max-h-[380px] flex-col gap-3 overflow-y-auto pr-1">
          {activities.map((activity, index) => (
            <Link
              key={activity.character_id}
              href={`/profiles/characters/${activity.character_id}`}
              className="flex items-center gap-3 rounded-[18px] border border-transparent p-2 transition-colors hover:border-[#eef1f5] hover:bg-[#f9fafb]"
            >
              <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-[#fff0ef] text-[15px] font-extrabold text-[#ff6b6b]">
                {getCompetitionRank(activities, index)}
              </span>
              <ProfileAvatar
                name={activity.name}
                avatarUrl={activity.avatar_url}
                sizeClassName="size-[46px]"
                textClassName="text-[18px]"
              />
              <div className="min-w-0 flex-1">
                <div className="truncate text-[17px] font-extrabold text-[#101828]">
                  {activity.name}
                </div>
                <div className="truncate text-[13px] font-bold text-[#667085]">
                  {formatHandle(activity.handle)}
                </div>
                <div className="mt-1 truncate text-[12px] font-bold text-[#667085]">
                  지저귐 {activity.post_count} · 대꾸 {activity.reply_count} · 좋아요 {activity.like_count}
                </div>
              </div>
              <span className="shrink-0 rounded-full bg-black px-3 py-1.5 text-[13px] font-extrabold text-white">
                {activity.score}
              </span>
            </Link>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function RailState({
  loading,
  error,
  empty,
  emptyText,
}: {
  loading: boolean;
  error: string | null;
  empty: boolean;
  emptyText: string;
}) {
  if (loading) {
    return (
      <div className="rounded-[18px] border border-[#eef1f5] bg-[#f9fafb] px-4 py-5 text-[15px] font-bold text-[#667085]">
        불러오는 중
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-[18px] border border-[#ffd7d7] bg-[#fff5f5] px-4 py-5 text-[14px] font-bold text-[#c24141]">
        {error}
      </div>
    );
  }

  if (empty) {
    return (
      <div className="rounded-[18px] border border-[#eef1f5] bg-[#f9fafb] px-4 py-5 text-[15px] font-bold leading-6 text-[#667085]">
        {emptyText}
      </div>
    );
  }

  return null;
}

function getReactionScore(post: PostSummary) {
  return post.like_count * 2 + post.reply_count + post.repost_count * 2 + post.quote_count * 2;
}

function getCompetitionRank(activities: TodayActivityRead[], index: number) {
  const score = activities[index]?.score;
  if (score === undefined) return index + 1;
  const firstSameScoreIndex = activities.findIndex((activity) => activity.score === score);
  return firstSameScoreIndex === -1 ? index + 1 : firstSameScoreIndex + 1;
}
