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

import { LocalProductLink } from "@/features/device-shell/public";
import {
  formatActionLabel,
  formatActivityDetail,
  formatActivityHeadline,
  formatTargetLinkLabel,
  targetProfileHref,
  type AgentActivityLogView,
} from "@/lib/activity";
import { formatDate } from "@/lib/community";
import { Badge, EmptyState } from "@/shared/ui/public";

export function AgentActivityList({
  logs,
  characterName,
  emptyText = "아직 활동 로그가 없습니다.",
  showActorName = true,
  timeZone = "Asia/Seoul",
}: {
  logs: AgentActivityLogView[];
  characterName: string;
  emptyText?: string;
  showActorName?: boolean;
  timeZone?: string;
}) {
  if (logs.length === 0) {
    return (
      <EmptyState
        description={emptyText}
        title="활동 기록 없음"
      />
    );
  }

  return (
    <div className="flex flex-col border-t border-border-default">
      <p
        className="border-b border-border-default bg-surface-subtle px-4 py-2 text-xs font-bold text-text-secondary"
        data-activity-log-timezone={timeZone}
      >
        표시 시간 · {timeZone}
      </p>
      {logs.map((log) => {
        const Icon = getActivityIcon(log.action_type);
        const detail = formatActivityDetail(log);
        const profileHref = targetProfileHref(log);

        return (
          <article key={log.id} className="border-b border-border-default bg-surface py-5">
            <div className="flex gap-4">
              <div className="flex size-11 shrink-0 items-center justify-center rounded-full bg-surface-muted text-text-secondary">
                <Icon size={20} aria-hidden="true" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <Badge>
                    {formatActionLabel(log.action_type)}
                  </Badge>
                  <time
                    dateTime={log.created_at}
                    className="text-[14px] font-medium text-text-secondary"
                    title={`${timeZone} 기준`}
                  >
                    {formatDate(log.created_at, timeZone)}
                  </time>
                </div>
                <p className="break-words text-[17px] font-extrabold leading-7 text-text-strong">
                  {formatActivityHeadline(log, characterName, { showActorName })}
                </p>
                {detail ? (
                  <p className="mt-1 break-words text-[15px] font-medium leading-6 text-text-secondary">
                    {detail}
                  </p>
                ) : null}
                {log.target_post_id ? (
                  <LocalProductLink
                    href={`/posts/${log.target_post_id}`}
                    title={log.target_post_id}
                    className="mt-3 inline-flex min-h-11 items-center rounded-full border border-border-control bg-surface px-4 py-2 text-[13px] font-extrabold text-text-strong transition-colors hover:border-brand-soft-border hover:bg-surface-subtle focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]"
                  >
                    {formatTargetLinkLabel(log.action_type)}
                  </LocalProductLink>
                ) : null}
                {!log.target_post_id && profileHref ? (
                  <LocalProductLink
                    href={profileHref}
                    className="mt-3 inline-flex min-h-11 items-center rounded-full border border-border-control bg-surface px-4 py-2 text-[13px] font-extrabold text-text-strong transition-colors hover:border-brand-soft-border hover:bg-surface-subtle focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]"
                  >
                    {formatTargetLinkLabel(log.action_type)}
                  </LocalProductLink>
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
