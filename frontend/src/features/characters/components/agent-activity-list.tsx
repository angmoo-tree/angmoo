"use client";
import { useUiDateFormatter } from "@/hooks/use-ui-date-formatter";
import { useUserEnvironment } from "@/hooks/use-user-environment";

import { useUiText } from "@/hooks/use-ui-text";


import { ActivityTimeline } from "@/components/content/activity-timeline";
import { getActivityIcon } from "@/features/characters/utils/activity-icons";
import {
  formatActionLabel,
  formatActivityDetail,
  formatActivityHeadline,
  formatTargetLinkLabel,
  targetProfileHref,
  type AgentActivityLogView,
} from "@/features/characters/utils/activity";

import { EmptyState } from "@/components/ui/feedback";

export function AgentActivityList({
  logs,
  characterName,
  emptyText: providedEmptyText,
  showActorName = true,
  timeZone: packageTimezone,
}: {
  logs: AgentActivityLogView[];
  characterName: string;
  emptyText?: string;
  showActorName?: boolean;
  timeZone?: string;
}) {
  const formatDate = useUiDateFormatter();
  void packageTimezone;
  const timeZone = useUserEnvironment().environment?.timezone ?? "UTC";
  const uiText = useUiText("characters");
  const emptyText = providedEmptyText ?? uiText("아직 활동 로그가 없습니다.");
  if (logs.length === 0) {
    return (
      <EmptyState
        description={emptyText}
        title={uiText("활동 기록 없음")}
      />
    );
  }

  return <ActivityTimeline timezone={timeZone} timezoneLabel={uiText("표시 시간 ·")} empty={null} items={logs.map(log => {
    const Icon = getActivityIcon(log.action_type);
    const href = log.target_post_id ? `/posts/${log.target_post_id}` : targetProfileHref(log);
    return {
      id: log.id, icon: <Icon size={20} aria-hidden="true" />,
      actionLabel: uiText(formatActionLabel(log.action_type)), occurredAt: log.created_at,
      displayedTime: formatDate(log.created_at, timeZone), timeTitle: uiText("{{value0}} 기준", { value0: timeZone }),
      headline: formatActivityHeadline(log, characterName, { showActorName, uiText }), detail: formatActivityDetail(log, uiText),
      link: href ? { href, label: uiText(formatTargetLinkLabel(log.action_type)), title: log.target_post_id ?? undefined } : undefined,
    };
  })} />;
}
