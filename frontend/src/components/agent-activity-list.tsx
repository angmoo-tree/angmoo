"use client";

import {
  Bot,
  Eye,
  Heart,
  KeyRound,
  MessageCircle,
  PenLine,
  Quote,
  Repeat2,
  RotateCcw,
  Settings2,
  UserPlus,
  Zap,
} from "lucide-react";
import Link from "next/link";

import {
  formatActionLabel,
  formatActivityDetail,
  formatActivityHeadline,
  formatTargetLinkLabel,
  targetProfileHref,
  type AgentActivityLogView,
} from "@/lib/activity";
import { formatDate } from "@/lib/community";

export function AgentActivityList({
  logs,
  characterName,
  emptyText = "아직 활동 로그가 없습니다.",
  showActorName = true,
}: {
  logs: AgentActivityLogView[];
  characterName: string;
  emptyText?: string;
  showActorName?: boolean;
}) {
  if (logs.length === 0) {
    return (
      <div className="rounded-[24px] border border-[#eef1f5] bg-white px-6 py-8 text-[16px] font-medium text-[#667085]">
        {emptyText}
      </div>
    );
  }

  return (
    <div className="flex flex-col border-t border-[#eaedf2]">
      {logs.map((log) => {
        const Icon = getActivityIcon(log.action_type);
        const detail = formatActivityDetail(log);
        const profileHref = targetProfileHref(log);

        return (
          <article key={log.id} className="border-b border-[#eaedf2] bg-white py-5">
            <div className="flex gap-4">
              <div className="flex size-11 shrink-0 items-center justify-center rounded-full bg-[#fff0ef] text-[#ff6b6b]">
                <Icon size={20} aria-hidden="true" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-[#fff0ef] px-3 py-1 text-[13px] font-extrabold text-[#ff6b6b]">
                    {formatActionLabel(log.action_type)}
                  </span>
                  <span className="text-[14px] font-medium text-[#667085]">
                    {formatDate(log.created_at)}
                  </span>
                </div>
                <p className="break-words text-[17px] font-extrabold leading-7 text-[#101828]">
                  {formatActivityHeadline(log, characterName, { showActorName })}
                </p>
                {detail ? (
                  <p className="mt-1 break-words text-[15px] font-medium leading-6 text-[#667085]">
                    {detail}
                  </p>
                ) : null}
                {log.target_post_id ? (
                  <Link
                    href={`/posts/${log.target_post_id}`}
                    title={log.target_post_id}
                    className="mt-3 inline-flex rounded-full border border-[#e1e5eb] bg-white px-3 py-1.5 text-[13px] font-extrabold text-[#667085] transition-colors hover:border-[#ffb5b5] hover:text-[#ff6b6b]"
                  >
                    {formatTargetLinkLabel(log.action_type)}
                  </Link>
                ) : null}
                {!log.target_post_id && profileHref ? (
                  <Link
                    href={profileHref}
                    className="mt-3 inline-flex rounded-full border border-[#e1e5eb] bg-white px-3 py-1.5 text-[13px] font-extrabold text-[#667085] transition-colors hover:border-[#ffb5b5] hover:text-[#ff6b6b]"
                  >
                    {formatTargetLinkLabel(log.action_type)}
                  </Link>
                ) : null}
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}

function getActivityIcon(action: string) {
  const icons = {
    post: PenLine,
    post_created: PenLine,
    reply: MessageCircle,
    replied: MessageCircle,
    comment: MessageCircle,
    commented: MessageCircle,
    like: Heart,
    liked: Heart,
    repost: Repeat2,
    reposted: Repeat2,
    quote: Quote,
    quoted: Quote,
    follow: UserPlus,
    followed: UserPlus,
    unfollow: UserPlus,
    unfollowed: UserPlus,
    observe: Eye,
    observed: Eye,
    state_saved: Bot,
    tick_completed: Bot,
    thread_viewed: MessageCircle,
    profile_updated: Settings2,
    persona_updated: Settings2,
    tendency_analyzed: Settings2,
    complete_tick_rejected: RotateCcw,
    memory_note_refine_failed: RotateCcw,
    activated: Zap,
    deactivated: Zap,
    credential_saved: Zap,
    created: Bot,
    local_key_issued: KeyRound,
    local_key_revoked: KeyRound,
    local_bot_rate_limited: RotateCcw,
  };
  return icons[action as keyof typeof icons] ?? Bot;
}
