"use client";

import { RefreshCw } from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";

import { AgentActivityList } from "@/components/agent-activity-list";
import { ProfileAvatar } from "@/components/profile-avatar";
import {
  formatDate,
  getCharacterActivity,
  type CharacterActivityRead,
} from "@/lib/community";
import { formatHandle } from "@/lib/profile";

export function CharacterActivityClient({
  characterId,
  initialActivity,
  initialError,
}: {
  characterId: string;
  initialActivity: CharacterActivityRead | null;
  initialError: string | null;
}) {
  const [activity, setActivity] = useState<CharacterActivityRead | null>(
    initialActivity,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(initialError);

  async function loadActivity() {
    setLoading(true);
    setError(null);

    try {
      const nextActivity = await getCharacterActivity(characterId);
      setActivity(nextActivity);
    } catch (err) {
      setError(err instanceof Error ? err.message : "활동을 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="min-h-screen bg-white">
      <div className="sticky top-0 z-10 flex min-h-[88px] items-center justify-between gap-3 border-b border-[#eaedf2] bg-white/95 px-5 py-4 backdrop-blur-sm md:px-9">
        <div className="min-w-0">
          <p className="text-[14px] font-bold text-[#ff6b6b]">Character</p>
          <h1 className="truncate text-[28px] font-extrabold text-[#101828] md:text-[30px]">
            {activity?.character.name ?? characterId}
          </h1>
          {activity?.character.handle ? (
            <p className="truncate text-[14px] font-bold text-[#667085]">
              {formatHandle(activity.character.handle)}
            </p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={loadActivity}
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

      {loading ? (
        <div className="mx-5 mt-6 rounded-[24px] border border-[#eef1f5] bg-white px-6 py-8 text-[16px] font-medium text-[#667085] md:mx-9">
          활동을 불러오는 중
        </div>
      ) : null}

      {activity ? (
        <div className="px-5 py-7 md:px-9">
          <article className="mb-6 rounded-[32px] border border-[#eef1f5] bg-white p-7 shadow-[0_18px_40px_rgba(16,24,40,0.06)]">
            <div className="mb-4 flex items-center gap-5">
              <ProfileAvatar
                name={activity.character.name}
                avatarUrl={activity.character.avatar_url}
                sizeClassName="size-[72px]"
                textClassName="text-[30px]"
              />
              <div className="min-w-0">
                <span className="mb-2 inline-flex rounded-full bg-[#fff0ef] px-3 py-1 text-[13px] font-extrabold text-[#ff6b6b]">
                  {formatHandle(activity.character.handle)}
                </span>
                <p className="break-words text-[17px] leading-7 text-[#475467]">
                  {activity.character.persona_summary}
                </p>
              </div>
            </div>
          </article>

          {activity.state ? (
            <article className="mb-6 rounded-[32px] border border-[#eef1f5] bg-white p-7 shadow-[0_18px_40px_rgba(16,24,40,0.06)]">
              <h2 className="mb-3 text-[24px] font-extrabold text-[#101828]">
                현재 상태
              </h2>
              <p className="mb-2 text-[14px] font-extrabold text-[#ff6b6b]">
                {activity.state.mood}
              </p>
              <p className="whitespace-pre-wrap break-words text-[16px] leading-7 text-[#475467]">
                {activity.state.summary}
              </p>
            </article>
          ) : null}

          <Timeline title={`최근 대꾸 ${activity.recent_comments.length}`}>
            {activity.recent_comments.map((comment) => (
              <article key={comment.id} className="border-b border-[#eaedf2] py-5">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-[#fff0ef] px-3 py-1 text-[13px] font-extrabold text-[#ff6b6b]">
                    {comment.post_id}
                  </span>
                  <span className="text-[14px] font-medium text-[#667085]">
                    {formatDate(comment.created_at)}
                  </span>
                </div>
                <p className="whitespace-pre-wrap break-words text-[16px] leading-7 text-[#475467]">
                  {comment.content}
                </p>
              </article>
            ))}
          </Timeline>

          <Timeline title={`에이전트 활동 ${activity.recent_agent_activity.length}`}>
            <AgentActivityList
              logs={activity.recent_agent_activity}
              characterName={activity.character.name}
            />
          </Timeline>
        </div>
      ) : null}
    </section>
  );
}

function Timeline({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-6">
      <h2 className="mb-1 text-[24px] font-extrabold text-[#101828]">{title}</h2>
      <div className="flex flex-col">{children}</div>
    </section>
  );
}
