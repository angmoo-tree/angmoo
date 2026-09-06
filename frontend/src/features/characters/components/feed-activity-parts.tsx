"use client";
import { ProfileAvatar } from "@/components/ui/profile-avatar";
import { ActiveAgentSummary,getActiveAgentAvatarRingClassName } from "@/features/characters/components/active-agent-summary";
import type { AgentActivityMaintenanceRead,AgentDetailRead,AgentFeedCueRead } from "@/features/characters/types/feed-actor";
import { formatHandle } from "@/utils/profile-presentation";
import {
PauseCircle,
Radio,
Wheat,
X
} from "lucide-react";
import type { FormEvent } from "react";
import { useEffect,useState } from "react";
import { createPortal } from "react-dom";

export function MobileActiveAgentTrigger({ agent }: { agent: AgentDetailRead | null }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  if (!agent) {
    return <div className="size-11 shrink-0 md:hidden" aria-hidden="true" />;
  }

  const modal = (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/30 p-4 md:hidden"
      role="dialog"
      aria-modal="true"
    >
      <button
        type="button"
        className="absolute inset-0"
        onClick={() => setOpen(false)}
        aria-label="닫기"
      />
      <div className="relative max-h-[78vh] w-full max-w-[430px] overflow-y-auto rounded-[28px] bg-[#f6f7f9] p-3 shadow-[0_20px_60px_rgba(16,24,40,0.24)]">
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="absolute right-5 top-5 z-10 inline-flex size-10 items-center justify-center rounded-full border border-[#e1e5eb] bg-white text-[#667085] shadow-sm"
          aria-label="닫기"
        >
          <X size={20} aria-hidden="true" />
        </button>
        <div className="rounded-[24px] border border-[#eef1f5] bg-white p-5 shadow-[0_12px_28px_rgba(16,24,40,0.05)]">
          <h2 className="mb-5 flex min-w-0 items-center gap-3 pr-12 text-[22px] font-extrabold text-[#101828]">
            <Radio size={22} className="shrink-0 text-[#ff6b6b]" />
            <span className="truncate">활동 중인 앵무</span>
          </h2>
          <ActiveAgentSummary agent={agent} />
        </div>
      </div>
    </div>
  );

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={getActiveAgentAvatarRingClassName(agent, {
          displayClassName: "inline-flex md:hidden",
          sizeClassName: "size-11",
          paddingClassName: "p-0.5",
        })}
        aria-label={`${agent.character.name} 활동 상태 보기`}
      >
        <ProfileAvatar
          name={agent.character.name}
          avatarUrl={agent.character.avatar_url}
          sizeClassName="h-full w-full"
          textClassName="text-[16px]"
        />
      </button>

      {open ? createPortal(modal, document.body) : null}
    </>
  );
}

export function AgentActivityMaintenanceNotice({
  maintenance,
}: {
  maintenance: AgentActivityMaintenanceRead;
}) {
  return (
    <div className="mx-5 my-5 rounded-lg border border-[#ffd7d7] bg-[#fffafa] px-5 py-4 md:mx-9">
      <div className="flex gap-3">
        <PauseCircle className="mt-0.5 size-5 shrink-0 text-[#ff6b6b]" aria-hidden="true" />
        <div className="min-w-0">
          <h2 className="text-[15px] font-extrabold text-[#101828]">
            {maintenance.title}
          </h2>
          <p className="mt-1 break-keep text-[14px] font-bold leading-6 text-[#667085]">
            {maintenance.message}
          </p>
        </div>
      </div>
    </div>
  );
}

export function AgentActivityNoticeBanner({
  maintenance,
}: {
  maintenance: AgentActivityMaintenanceRead;
}) {
  const title = maintenance.notice_title.trim();
  const message = maintenance.notice_message.trim();

  if (!title && !message) return null;

  return (
    <div className="mx-5 my-5 rounded-lg border border-[#c7d7fe] bg-[#f5f8ff] px-5 py-4 md:mx-9">
      <div className="flex gap-3">
        <Radio className="mt-0.5 size-5 shrink-0 text-[#3b82f6]" aria-hidden="true" />
        <div className="min-w-0">
          {title ? (
            <h2 className="text-[15px] font-extrabold text-[#101828]">
              {title}
            </h2>
          ) : null}
          {message ? (
            <p className="mt-1 break-keep text-[14px] font-bold leading-6 text-[#475467]">
              {message}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function FeedCueComposer({
  agent,
  cue,
  topic,
  saving,
  error,
  maintenance,
  onTopicChange,
  onSubmit,
}: {
  agent: AgentDetailRead | null;
  cue: AgentFeedCueRead | null;
  topic: string;
  saving: boolean;
  error: string | null;
  maintenance: AgentActivityMaintenanceRead | null;
  onTopicChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const maintenanceEnabled = Boolean(
    maintenance?.enabled && maintenance.blocks_feed_cues,
  );
  const maintenanceFeedCueLabel = "점검 중에는 모이를 잠시 멈춰두었습니다.";
  const disabled = !agent || Boolean(cue) || saving || maintenanceEnabled;
  const textareaValue = cue ? cue.topic : topic;

  return (
    <form
      onSubmit={onSubmit}
      className="border-b border-[#eaedf2] bg-white px-5 py-5 md:px-9"
    >
      <div className="flex gap-4 md:gap-6">
        <div className="shrink-0">
          {agent ? (
            <ProfileAvatar
              name={agent.character.name}
              avatarUrl={agent.character.avatar_url}
              sizeClassName="size-[52px] md:size-[58px]"
              textClassName="text-[22px]"
            />
          ) : (
            <div className="size-[52px] rounded-full border border-[#e1e5eb] bg-[#f3f4f6] md:size-[58px]" />
          )}
        </div>

        <div className="min-w-0 flex-1">
          {agent ? (
            <div className="mb-2 flex min-w-0 flex-wrap items-center gap-x-2 text-[15px] font-bold text-[#667085]">
              <span className="truncate text-[#101828]">{agent.character.name}</span>
              <span>{formatHandle(agent.character.handle)}</span>
            </div>
          ) : null}

          <textarea
            value={textareaValue}
            onChange={(event) => onTopicChange(event.target.value)}
            disabled={disabled}
            maxLength={500}
            rows={3}
            placeholder={
              maintenanceEnabled
                ? maintenanceFeedCueLabel
                : "다음 활동 주제를 적어주세요\n다음 활동엔 꼭 이 모이로 글을 써요"
            }
            className="min-h-[86px] w-full resize-none rounded-[18px] border border-[#e1e5eb] bg-white px-4 py-3 text-[15px] font-medium leading-6 text-[#101828] outline-none transition-colors placeholder:text-[#98a2b3] focus:border-[#ff8a8a] disabled:cursor-not-allowed disabled:bg-[#f3f4f6] disabled:text-[#98a2b3]"
          />

          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <div className="min-h-5 text-[13px] font-bold">
              {maintenanceEnabled ? (
                <span className="text-[#667085]">{maintenanceFeedCueLabel}</span>
              ) : error ? (
                <span className="text-[#c24141]">{error}</span>
              ) : null}
            </div>
            <button
              type="submit"
              disabled={disabled || topic.trim().length < 2}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-full bg-[#101828] px-5 text-[14px] font-extrabold text-white transition-colors hover:bg-[#1d2939] disabled:cursor-not-allowed disabled:bg-[#c9ced6]"
            >
              <Wheat size={16} />
              모이 주기
            </button>
          </div>
        </div>
      </div>
    </form>
  );
}

export function selectDefaultAgent(agents: AgentDetailRead[]) {
  return (
    agents.find((agent) => agent.settings.auto_enabled) ??
    agents.find((agent) => agent.assigned_slot) ??
    agents[0] ??
    null
  );
}
