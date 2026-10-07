"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/surfaces";
import { PersonaStatusCard, ActivitySummaryStatusCard, CurrentStateStatusCard, RecentActivityStatusCard } from "@/components/ui/status-cards";
import { ActivityTimeline } from "@/components/content/activity-timeline";
import { EmptyState } from "@/components/ui/feedback";
import { useUiText } from "@/hooks/use-ui-text";
import { useAuth } from "@/hooks/use-auth";
import { useUiDateFormatter } from "@/hooks/use-ui-date-formatter";
import { useContainerIncrementalCount } from "@/hooks/use-incremental-list";
import { useUserEnvironment } from "@/hooks/use-user-environment";
import { worldPostDetailRoute } from "@/lib/navigation/product-routes";
import { formatHandle } from "@/utils/profile-presentation";
import { getActivityIcon } from "../utils/activity-icons";
import { presentWorldRecentActivity } from "../utils/world-character-status-presentation";
import type { WorldCharacterPublicProfile } from "../types/world-character-profile";
import { presentWorldCharacterState } from "../utils/world-character-dashboard-presentation";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { ApiRequestError } from "@/lib/http/api-request";
import { DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT } from "@/lib/runtime/runtime-config";
import { getWorldCharacterStatus, type WorldCharacterStatus } from "../api/world-character-status";

const FIELDS = [["worldview", "캐릭터 설명"], ["personality", "성격"], ["speech_style", "말투"],
  ["character_background", "캐릭터 배경·세계관"], ["topic_preferences", "관심 주제"], ["safety_rules", "피해야 할 행동/표현"]] as const;
const ACTIONS: Record<string, string> = { reply: "답글 작성", comment: "답글 작성", post: "게시글 작성", like: "좋아요" };

export function WorldCharacterStatusCards({ worldId, actorId, profile, revision, active }: { worldId: string; actorId: string; profile: WorldCharacterPublicProfile; revision: number; active: boolean }) {
  const uiText = useUiText("characters"), { status, user } = useAuth();
  const formatDate = useUiDateFormatter();
  const displayTimezone = useUserEnvironment().environment?.timezone ?? "UTC";
  const [read, setRead] = useState<WorldCharacterStatus | null>(null);
  const [error, setError] = useState(false), [loading, setLoading] = useState(false), [retry, setRetry] = useState(0);
  const [runtime, setRuntime] = useState(0);
  const [receivedScope, setReceivedScope] = useState<ReturnType<typeof captureAuthRequestScope> | null>(null);
  useEffect(() => {
    const changed = () => { setReceivedScope(null); setRead(null); setRuntime(value => value + 1); };
    window.addEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, changed);
    return () => window.removeEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, changed);
  }, []);
  useEffect(() => {
    if (!active || status !== "authenticated") return;
    const controller = new AbortController(), scope = captureAuthRequestScope();
    let current = true;
    queueMicrotask(() => { if (current) setLoading(true); });
    void getWorldCharacterStatus(worldId, actorId, controller.signal).then(value => {
      if (!current || !isCurrentAuthRequestScope(scope) || value.revision < revision) return;
      setReceivedScope(scope); setRead(value); setError(false);
    }).catch(reason => {
      if (!current || !isCurrentAuthRequestScope(scope)) return;
      if (reason instanceof ApiRequestError && [401, 403, 404].includes(reason.status)) { setReceivedScope(null); setRead(null); }
      setError(true);
    }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; controller.abort(); };
  }, [active, status, user?.id, worldId, actorId, revision, retry, runtime]);
  const visible = receivedScope && isCurrentAuthRequestScope(receivedScope) && read?.world_id === worldId && read.world_character_id === actorId ? read : null;
  const { visibleCount, handleScroll } = useContainerIncrementalCount(
    visible?.recent_activity.length ?? 0,
    `${worldId}:${actorId}:${visible?.recent_activity.length ?? 0}:${visible?.recent_activity[0]?.id ?? ""}`,
    5, 10,
  );
  if (!visible) return <Card><p role="status">{uiText(loading ? "상태를 불러오는 중..." : error ? "상태를 불러오지 못했어요." : "아직 상태 정보가 없어요.")}</p>
    {error ? <Button variant="secondary" onClick={() => setRetry(value => value + 1)}>{uiText("다시 시도")}</Button> : null}</Card>;
  const summary = visible.summary;
  const state = presentWorldCharacterState({ profile: { control_mode: "autonomous" }, autonomous_enabled: visible.autonomous_enabled, status: visible.state, next_activity_at: visible.next_activity_at });
  return <div className="grid min-w-0 gap-6">
    {error ? <Card><p role="alert">{uiText("상태를 불러오지 못했어요.")}</p><Button variant="secondary" onClick={() => setRetry(value => value + 1)}>{uiText("다시 시도")}</Button></Card> : null}
    <CurrentStateStatusCard name={profile.display_name} avatarUrl={profile.avatar_url}
      badges={[
        { label: uiText(state.label), tone: state.tone === "danger" ? "danger" : visible.autonomous_enabled ? "accent" : "neutral" },
        ...(profile.handle ? [{ label: formatHandle(profile.handle) }] : []),
      ]} description={profile.intro} metadata={[
        { label: uiText("최근 활동"), value: visible.recent_activity[0] ? <time dateTime={visible.recent_activity[0].occurred_at}>{formatDate(visible.recent_activity[0].occurred_at)}</time> : "-" },
        { label: uiText("다음 활동"), value: visible.next_activity_at ? <time dateTime={visible.next_activity_at}>{formatDate(visible.next_activity_at)}</time> : "-" },
      ]} />
    <RecentActivityStatusCard title={uiText("최근 활동")} onScroll={handleScroll}>
      <ActivityTimeline timezone={displayTimezone} timezoneLabel={uiText("표시 시간 ·")}
        empty={<EmptyState title={uiText("활동 기록 없음")} description={uiText("최근 활동이 없습니다.")} />}
        items={visible.recent_activity.slice(0, visibleCount).map(row => {
          const Icon = getActivityIcon(row.action), presentation = presentWorldRecentActivity(row);
          return {
            id: row.id, icon: <Icon size={20} aria-hidden="true" />,
            actionLabel: uiText(ACTIONS[row.action] ?? "활동"), occurredAt: row.occurred_at,
            displayedTime: formatDate(row.occurred_at), timeTitle: uiText("{{value0}} 기준", { value0: displayTimezone }),
            headline: presentation.completed ? uiText(presentation.headline) : `${uiText(ACTIONS[row.action] ?? "활동")} · ${uiText(presentation.headline)}`,
            detail: row.title || (presentation.detail ? uiText(presentation.detail) : undefined),
            link: row.post_id ? { href: worldPostDetailRoute(worldId, row.post_id), label: uiText(presentation.linkLabel) } : undefined,
          };
        })} />
    </RecentActivityStatusCard>
    <PersonaStatusCard title={uiText("캐릭터 페르소나")} sections={FIELDS.filter(([key]) => visible.persona[key].trim()).map(([key, label]) => ({ label: uiText(label), value: visible.persona[key] }))} />
    <ActivitySummaryStatusCard title={uiText("활동 요약")} time={<>{uiText(visible.state.state === "outside_hours" ? "쉬는 시간대" : "활동 시간대")}<br />{summary.active_hours}</>} metrics={[
      { label: uiText("오늘 게시글 작성"), value: `${summary.posts}/${summary.post_limit}` }, { label: uiText("오늘 리플 작성"), value: `${summary.replies}/${summary.reply_limit}` },
      { label: uiText("오늘 좋아요"), value: uiText("{{value0}}회", { value0: summary.likes }) },
      { label: uiText("가능한 행동"), value: ["reply", "post", "like"].filter(action => summary.allowed_actions.includes(action)).map(action => uiText(ACTIONS[action])).join(", ") || uiText("없음") },
    ]} />
  </div>;
}
