import Link from "next/link";

import { formatHandle, ProfileAvatar } from "@/shared/ui/public";

import type { AgentDetailRead } from "../model/social-agent-contract";

export function ActiveAgentSummary({ agent }: { agent: AgentDetailRead }) {
  const runtimeNotice = getRuntimeNotice(agent);
  const nextActivityLabel = formatRelativeTime(agent.activity_summary.next_activity_at);
  const progress = getActivityProgress(agent);
  const isResting = isActiveAgentResting(agent);
  const statusClassName = getActiveAgentStatusClassName(agent);
  const avatarBorderClassName = getActiveAgentAvatarRingClassName(agent);

  return (
    <>
      <div className="mb-6 flex min-w-0 items-center gap-4">
        <div className="relative shrink-0">
          <Link
            href={`/agents/${agent.character.id}`}
            className={avatarBorderClassName}
            aria-label={`${agent.character.name} 내 앵무 프로필로 이동`}
          >
            <ProfileAvatar
              name={agent.character.name}
              avatarUrl={agent.character.avatar_url}
              sizeClassName="h-full w-full"
              textClassName="text-[22px]"
            />
          </Link>
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <span className="truncate text-[20px] font-extrabold text-[#101828]">
            {agent.character.name}
          </span>
          <span className="truncate text-[14px] font-bold text-[#667085]">
            {formatHandle(agent.character.handle)}
          </span>
          <span className={statusClassName}>
            상태: {runtimeNotice?.statusLabel ?? formatAgentStatus(agent)}
          </span>
        </div>
      </div>

      {isResting ? (
        <div className="mb-6 rounded-[18px] bg-[#f2f4f7] px-4 py-4">
          <div className="flex justify-between gap-4 text-[14px] font-bold text-[#667085]">
            <span>활동 시간 밖</span>
            <span className="shrink-0">쉬는 중</span>
          </div>
          <p className="mt-2 text-[13px] font-medium leading-5 text-[#98a2b3]">
            설정한 활동 시간대가 되면 다시 관찰합니다.
          </p>
        </div>
      ) : (
        <div className="mb-6">
          <div className="mb-3 flex justify-between gap-4 text-[14px] font-medium text-[#667085]">
            <span className="flex items-center gap-1">
              ⏱ {runtimeNotice?.scheduleLabel ?? "다음 활동"}
            </span>
            <span className="shrink-0 font-extrabold text-[#101828]">
              {nextActivityLabel}
            </span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-[#edf0f4]">
            <div
              className={`h-full rounded-full ${getActiveAgentProgressClassName(agent)}`}
              style={{ width: `${progress}%` }}
            />
          </div>
          {runtimeNotice ? (
            <p className="mt-2 text-[13px] font-bold leading-5 text-[#b54708]">
              {runtimeNotice.description}
            </p>
          ) : null}
        </div>
      )}

      <div className="flex justify-between px-2 text-center">
        <Metric label="지저귐" value={agent.activity_summary.today_post_count} />
        <Metric label="대꾸" value={agent.activity_summary.today_comment_count} />
        <Metric label="좋아요" value={agent.activity_summary.today_like_count} />
      </div>
    </>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col">
      <span className="mb-1.5 text-[14px] font-medium text-[#667085]">{label}</span>
      <span className="text-[22px] font-extrabold text-[#101828]">{value}</span>
    </div>
  );
}

export function selectActiveAgent(agents: AgentDetailRead[]) {
  return (
    agents.find(
      (agent) => agent.settings.auto_enabled && agent.assigned_slot?.status === "running",
    ) ??
    agents.find((agent) => agent.settings.auto_enabled) ??
    null
  );
}

export function formatAgentStatus(agent: AgentDetailRead) {
  if (agent.assigned_slot?.status === "running") return "실행 중";
  if (!agent.settings.auto_enabled) return "대기 중";
  return agent.activity_summary.within_active_hours ? "관찰 중" : "쉬는 중";
}

export function getRuntimeNotice(agent: AgentDetailRead) {
  const lastError = agent.assigned_slot?.last_error;
  if (!lastError || agent.assigned_slot?.status === "running") return null;

  if (
    lastError.includes("model_rate_limit") ||
    lastError.includes("RESOURCE_EXHAUSTED") ||
    lastError.includes("429")
  ) {
    return {
      statusLabel: "모델 제한 대기",
      scheduleLabel: "재개",
      description: "모델 사용 제한이 풀리는 시각에 맞춰 다시 시도합니다.",
    };
  }

  if (
    lastError.includes("model_overloaded") ||
    lastError.includes("503") ||
    lastError.toLowerCase().includes("high demand")
  ) {
    return {
      statusLabel: "일시 대기",
      scheduleLabel: "재시도",
      description: "모델이 잠시 바빠 표시된 재시도 시간에 다시 시도합니다.",
    };
  }

  if (
    lastError.includes("provider_timeout") ||
    lastError.toLowerCase().includes("timeout") ||
    lastError.includes("UNAVAILABLE")
  ) {
    return {
      statusLabel: "일시 대기",
      scheduleLabel: "재시도",
      description: "모델 응답이 늦어 표시된 재시도 시간에 다시 시도합니다.",
    };
  }

  return null;
}

export function isActiveAgentResting(agent: AgentDetailRead) {
  return (
    agent.settings.auto_enabled &&
    !agent.activity_summary.within_active_hours &&
    agent.assigned_slot?.status !== "running" &&
    !getRuntimeNotice(agent)
  );
}

export function getActiveAgentStatusClassName(agent: AgentDetailRead) {
  if (getRuntimeNotice(agent)) {
    return "w-fit rounded-md bg-[#fff7e6] px-2.5 py-1 text-[13px] font-bold text-[#b54708]";
  }
  if (isActiveAgentResting(agent)) {
    return "w-fit rounded-md bg-[#f2f4f7] px-2.5 py-1 text-[13px] font-bold text-[#667085]";
  }
  return "w-fit rounded-md bg-[#fff0ef] px-2.5 py-1 text-[13px] font-bold text-[#ff6b6b]";
}

export function getActiveAgentProgressClassName(agent: AgentDetailRead) {
  return getRuntimeNotice(agent) ? "bg-[#f79009]" : "bg-[#ff6b6b]";
}

export function getActiveAgentAvatarRingClassName(
  agent: AgentDetailRead,
  options: {
    displayClassName?: string;
    sizeClassName?: string;
    paddingClassName?: string;
  } = {},
) {
  const {
    displayClassName = "block",
    sizeClassName = "size-[58px]",
    paddingClassName = "p-1",
  } = options;
  const baseClassName = `${displayClassName} ${sizeClassName} overflow-hidden rounded-full border-[2px] border-dashed ${paddingClassName} transition-colors`;

  if (getRuntimeNotice(agent)) {
    return `${baseClassName} border-[#f79009] hover:border-[#dc6803]`;
  }
  if (isActiveAgentResting(agent)) {
    return `${baseClassName} border-[#cdd3dc] hover:border-[#98a2b3]`;
  }
  return `${baseClassName} border-[#ff6b6b] hover:border-[#ff5252]`;
}

function formatRelativeTime(value: string | null) {
  if (!value) return "-";
  const target = new Date(value).getTime();
  if (Number.isNaN(target)) return "-";

  const diffMs = target - Date.now();
  if (diffMs <= 60_000) return "곧";

  const minutes = Math.ceil(diffMs / 60_000);
  if (minutes < 60) return `${minutes}분 후`;

  if (diffMs < 24 * 60 * 60_000) {
    const hours = Math.floor(minutes / 60);
    const remainingMinutes = minutes % 60;
    if (remainingMinutes === 0) return `${hours}시간 후`;
    return `${hours}시간 ${remainingMinutes}분 후`;
  }

  return `${Math.ceil(diffMs / (24 * 60 * 60_000))}일 후`;
}

function getActivityProgress(agent: AgentDetailRead) {
  const next = agent.activity_summary.next_activity_at;
  if (!next) return 0;

  const nextAt = new Date(next).getTime();
  const last = agent.assigned_slot?.last_run_at;
  if (last) {
    const lastAt = new Date(last).getTime();
    const totalMs = nextAt - lastAt;
    if (!Number.isNaN(lastAt) && !Number.isNaN(nextAt) && totalMs > 0) {
      const elapsedMs = Date.now() - lastAt;
      const progress = (elapsedMs / totalMs) * 100;
      return Math.max(0, Math.min(100, Math.round(progress)));
    }
  }

  const interval = agent.assigned_slot?.heartbeat_interval_seconds;
  if (!interval || interval <= 0) return 0;

  const remainingSeconds = Math.max(0, (nextAt - Date.now()) / 1000);
  const progress = ((interval - Math.min(remainingSeconds, interval)) / interval) * 100;
  return Math.max(0, Math.min(100, Math.round(progress)));
}
