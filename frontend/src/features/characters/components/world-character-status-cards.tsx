"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/surfaces";
import { PersonaStatusCard, ActivitySummaryStatusCard } from "@/components/ui/status-cards";
import { useUiText } from "@/hooks/use-ui-text";
import { useAuth } from "@/hooks/use-auth";
import { useUiDateFormatter } from "@/hooks/use-ui-date-formatter";
import { LocalProductLink } from "@/components/navigation/local-product-link";
import { worldPostDetailRoute } from "@/lib/navigation/product-routes";
import { presentWorldCharacterState } from "../utils/world-character-dashboard-presentation";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { ApiRequestError } from "@/lib/http/api-request";
import { DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT } from "@/lib/runtime/runtime-config";
import { getWorldCharacterStatus, type WorldCharacterStatus } from "../api/world-character-status";

const FIELDS = [["worldview", "캐릭터 설명"], ["personality", "성격"], ["speech_style", "말투"],
  ["character_background", "캐릭터 배경·세계관"], ["topic_preferences", "관심 주제"], ["safety_rules", "피해야 할 행동/표현"]] as const;
const ACTIONS: Record<string, string> = { reply: "답글 작성", comment: "답글 작성", post: "게시글 작성", like: "좋아요" };
const OUTCOMES: Record<string, string> = { pending: "준비 중", running: "진행 중", completed: "완료", succeeded: "완료", success: "완료", ok: "완료", failed: "실패", blocked: "실행 보류", skipped: "건너뜀", cancelled: "취소됨" };

export function WorldCharacterStatusCards({ worldId, actorId, revision, active }: { worldId: string; actorId: string; revision: number; active: boolean }) {
  const uiText = useUiText("characters"), { status, user } = useAuth();
  const formatDate = useUiDateFormatter();
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
  if (!visible) return <Card><p role="status">{uiText(loading ? "상태를 불러오는 중..." : error ? "상태를 불러오지 못했어요." : "아직 상태 정보가 없어요.")}</p>
    {error ? <Button variant="secondary" onClick={() => setRetry(value => value + 1)}>{uiText("다시 시도")}</Button> : null}</Card>;
  const summary = visible.summary;
  const state = presentWorldCharacterState({ profile: { control_mode: "autonomous" }, autonomous_enabled: visible.autonomous_enabled, status: visible.state, next_activity_at: visible.next_activity_at });
  return <div className="grid min-w-0 gap-6">
    {error ? <Card><p role="alert">{uiText("상태를 불러오지 못했어요.")}</p><Button variant="secondary" onClick={() => setRetry(value => value + 1)}>{uiText("다시 시도")}</Button></Card> : null}
    <Card as="section"><h2 className="text-xl font-extrabold">{uiText("현재 상태")}</h2><p>{uiText(state.label)}</p>
      {visible.next_activity_at ? <time dateTime={visible.next_activity_at}>{formatDate(visible.next_activity_at, visible.timezone)}</time> : null}</Card>
    <Card as="section"><h2 className="text-xl font-extrabold">{uiText("최근 활동")}</h2>
      {visible.recent_activity.length ? <ol className="grid gap-3">{visible.recent_activity.map(row => <li key={row.id} className="min-w-0 rounded-xl bg-surface-muted p-4">
        <p className="font-bold">{uiText(ACTIONS[row.action] ?? "활동")} · {uiText(OUTCOMES[row.status] ?? "확인 필요")}</p>{row.title ? <p className="break-words">{row.title}</p> : null}<time dateTime={row.occurred_at}>{formatDate(row.occurred_at, visible.timezone)}</time>
        {row.post_id ? <LocalProductLink href={worldPostDetailRoute(worldId, row.post_id)} className="flex min-h-11 items-center text-action-primary">{uiText("게시글 열기")}</LocalProductLink> : null}
      </li>)}</ol> : <p>{uiText("아직 최근 활동이 없어요.")}</p>}</Card>
    <PersonaStatusCard title={uiText("캐릭터 페르소나")} sections={FIELDS.filter(([key]) => visible.persona[key].trim()).map(([key, label]) => ({ label: uiText(label), value: visible.persona[key] }))} />
    <ActivitySummaryStatusCard title={uiText("활동 요약")} time={summary.active_hours} metrics={[
      { label: uiText("오늘 게시글 작성"), value: `${summary.posts}/${summary.post_limit}` }, { label: uiText("오늘 리플 작성"), value: `${summary.replies}/${summary.reply_limit}` },
      { label: uiText("오늘 좋아요"), value: uiText("{{value0}}회", { value0: summary.likes }) },
      { label: uiText("가능한 행동"), value: ["reply", "post", "like"].filter(action => summary.allowed_actions.includes(action)).map(action => uiText(ACTIONS[action])).join(", ") || uiText("없음") },
    ]} />
  </div>;
}
