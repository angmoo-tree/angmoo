"use client";

import { Activity, ChevronRight, Power, PowerOff, RotateCcw, Users } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { LocalProductLink } from "@/components/navigation/local-product-link";
import { Button } from "@/components/ui/button";
import { InlineError } from "@/components/ui/feedback";
import { StatusChip } from "@/components/ui/status";
import { useAuth } from "@/hooks/use-auth";
import { useUiDateFormatter } from "@/hooks/use-ui-date-formatter";
import { useUiNumberFormatter } from "@/hooks/use-ui-number-formatter";
import { useUiText } from "@/hooks/use-ui-text";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { ApiRequestError } from "@/lib/http/api-request";
import { DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT } from "@/lib/runtime/runtime-config";
import { worldCharacterProfileRoute, worldPostDetailRoute } from "@/lib/navigation/product-routes";
import { getWorldCharacterDashboard, setWorldCharacterAutonomy } from "../api/world-character-dashboard-client";
import { WorldCharacterProfileApiError } from "../api/world-character-profile-client";
import type { WorldCharacterDashboardItem, WorldCharacterDashboardRead } from "../types/world-character-dashboard";
import { presentWorldCharacterState, sortWorldCharactersForDashboard, worldCharacterRestrictionMessage } from "../utils/world-character-dashboard-presentation";
import { CharacterManagementCard, CharacterManagementMetric } from "./character-management-card";
import styles from "./world-character-profile.module.css";
import cardStyles from "./characters-dashboard.module.css";

export function WorldCharacterDirectory({ worldId }: { worldId: string }) {
  const uiText = useUiText("characters");
  const formatNumber = useUiNumberFormatter();
  const { status, user } = useAuth();
  const [read, setRead] = useState<WorldCharacterDashboardRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [pending, setPending] = useState<Set<string>>(new Set());
  const root = useRef<HTMLElement>(null);
  const requests = useRef(new Set<AbortController>());
  const pendingTargets = useRef(new Set<string>());
  const lifetime = useRef(0);
  const mutationRevision = useRef(0);

  const load = useCallback(async () => {
    if (status !== "authenticated") return;
    const generation = lifetime.current;
    const revision = mutationRevision.current;
    const authScope = captureAuthRequestScope();
    const controller = new AbortController();
    requests.current.add(controller);
    setError(null);
    try {
      const result = await getWorldCharacterDashboard(worldId, { signal: controller.signal });
      if (!controller.signal.aborted && generation === lifetime.current && revision === mutationRevision.current && isCurrentAuthRequestScope(authScope)) {
        setRead(result);
        setLoading(false);
      }
    } catch (reason) {
      if (controller.signal.aborted || generation !== lifetime.current || revision !== mutationRevision.current || !isCurrentAuthRequestScope(authScope)) return;
      setError(reason instanceof Error ? reason : new Error("world_character_dashboard_unavailable"));
      if (reason instanceof ApiRequestError && [401, 403, 404].includes(reason.status)) setRead(null);
      setLoading(false);
    } finally {
      requests.current.delete(controller);
    }
  }, [status, worldId]);

  useEffect(() => {
    let active = true;
    const currentRequests = requests.current;
    lifetime.current += 1;
    requests.current.forEach((controller) => controller.abort());
    pendingTargets.current.clear();
    queueMicrotask(() => { if (active) { setRead(null); setPending(new Set()); setLoading(true); void load(); } });
    const invalidate = () => {
      lifetime.current += 1;
      requests.current.forEach((controller) => controller.abort());
      pendingTargets.current.clear();
      setRead(null); setPending(new Set()); setLoading(true); void load();
    };
    window.addEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, invalidate);
    return () => {
      active = false;
      lifetime.current += 1;
      currentRequests.forEach((controller) => controller.abort());
      window.removeEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, invalidate);
    };
  }, [load, user?.id]);

  async function toggle(item: WorldCharacterDashboardItem) {
    const id = item.profile.world_character_id;
    const allowed = item.autonomous_enabled ? item.capabilities.can_deactivate : item.capabilities.can_activate;
    if (!allowed || pendingTargets.current.has(id)) return;
    pendingTargets.current.add(id);
    setPending(new Set(pendingTargets.current));
    const generation = lifetime.current;
    const scope = captureAuthRequestScope();
    const controller = new AbortController();
    const restoreAnchor = preserveDirectoryAnchor(root.current);
    requests.current.add(controller);
    setError(null);
    try {
      const result = await setWorldCharacterAutonomy(worldId, id, !item.autonomous_enabled, item.revision, { signal: controller.signal });
      if (controller.signal.aborted || generation !== lifetime.current || !isCurrentAuthRequestScope(scope)) return;
      mutationRevision.current += 1;
      // Concurrent commands may complete out of order. A row's saved revision owns its value.
      setRead((current) => {
        if (!current) return result;
        const currentById = new Map(current.items.map((entry) => [entry.profile.world_character_id, entry]));
        const items = result.items.map((entry) => {
          const previous = currentById.get(entry.profile.world_character_id);
          return previous && previous.revision > entry.revision ? previous : entry;
        });
        const users = items.filter((entry) => entry.profile.control_mode === "owner_controlled").length;
        const enabled = items.filter((entry) => entry.profile.control_mode === "autonomous" && entry.autonomous_enabled).length;
        return { ...result, items, summary: { total: items.length, users, enabled, disabled: items.length - users - enabled } };
      });
      requestAnimationFrame(restoreAnchor);
    } catch (reason) {
      if (controller.signal.aborted || generation !== lifetime.current || !isCurrentAuthRequestScope(scope)) return;
      setError(reason instanceof Error ? reason : new Error("world_character_autonomy_failed"));
      if (reason instanceof ApiRequestError && [401, 403, 404].includes(reason.status)) setRead(null);
    } finally {
      requests.current.delete(controller);
      if (generation === lifetime.current) {
        pendingTargets.current.delete(id); setPending(new Set(pendingTargets.current));
      }
    }
  }

  return (
    <section ref={root} className={styles.directory} data-world-character-surface="list" data-character-dashboard="world-management">
      <header className={styles.directoryHeading}>
        <span className={styles.headingIcon} data-world-character-directory-icon><Users aria-hidden="true" size={21} /></span>
        <div><h2>{uiText("이 World의 앵무")}</h2>
          <span className={styles.directoryMeta}>{read ? uiText("현재 참여 중인 캐릭터 {{count}}명", { count: formatNumber(read.summary.total) }) : uiText("Character 목록을 불러오는 중")}</span>
        </div>
      </header>
      {read ? <p className={cardStyles.summary} data-character-summary>{uiText("World 캐릭터 집계", {
        total: formatNumber(read.summary.total), enabled: formatNumber(read.summary.enabled), disabled: formatNumber(read.summary.disabled), users: formatNumber(read.summary.users),
      })}</p> : null}
      {error ? read ? <InlineError className={cardStyles.feedback}><p>{uiText(worldCharacterOperationError(error))}</p><Button variant="secondary" compact onClick={() => void load()}>{uiText("다시 시도")}</Button></InlineError> : <ProfileError error={error} onRetry={() => void load()} /> : null}
      {loading && !read ? <ProfileStatus title={uiText("Character 목록을 불러오는 중")} /> : null}
      {read?.items.length === 0 ? <div className={styles.empty}><Users aria-hidden="true" size={28} /><h3>{uiText("현재 참여 중인 Character가 없어요")}</h3></div> : null}
      {read ? <div className={cardStyles.list} aria-label={uiText("World Character 목록")}>
        {sortWorldCharactersForDashboard(read.items).map((item) => <WorldCharacterManagementItem key={item.profile.world_character_id} item={item} pending={pending.has(item.profile.world_character_id)} onToggle={() => void toggle(item)} />)}
      </div> : null}
    </section>
  );
}

export function WorldCharacterManagementItem({ item, pending = false, onToggle }: { item: WorldCharacterDashboardItem; pending?: boolean; onToggle?: () => void }) {
  const uiText = useUiText("characters");
  const formatDate = useUiDateFormatter();
  const formatNumber = useUiNumberFormatter();
  const profile = item.profile;
  const isUser = profile.control_mode === "owner_controlled";
  const presentation = presentWorldCharacterState(item);
  const zone = item.settings?.timezone ?? "UTC";
  const toggleAllowed = item.autonomous_enabled ? item.capabilities.can_deactivate : item.capabilities.can_activate;
  const recent = item.recent_activity;
  return <CharacterManagementCard identity={{ id: profile.character_id, name: profile.display_name, handle: profile.handle, avatarUrl: profile.avatar_url, intro: profile.intro }}
    href={worldCharacterProfileRoute(profile.world_id, profile.world_character_id)} linkLabel={uiText("{{value0}}의 World 프로필 열기", { value0: profile.display_name })}
    worldCharacterId={profile.world_character_id} autonomyState={isUser ? "user" : item.autonomous_enabled ? "on" : "off"}
    status={<StatusChip label={uiText(presentation.label)} tone={presentation.tone} />}
    action={!isUser && onToggle ? <Button compact variant={item.autonomous_enabled ? "strong" : "primary"} loading={pending} disabled={pending || !toggleAllowed}
      aria-label={uiText("{{value0}} 자율활동 {{value1}}", { value0: profile.display_name, value1: uiText(item.autonomous_enabled ? "끄기" : "켜기") })}
      title={!toggleAllowed ? uiText(worldCharacterRestrictionMessage(item.capabilities.reason)) : undefined}
      loadingLabel={uiText(item.autonomous_enabled ? "끄는 중..." : "키는 중...")} onClick={onToggle}>
      {item.autonomous_enabled ? <PowerOff size={16} aria-hidden="true" /> : <Power size={16} aria-hidden="true" />}{uiText(item.autonomous_enabled ? "끄기" : "켜기")}
    </Button> : null}
    metrics={isUser ? <><CharacterManagementMetric label={uiText("활동 방식")} value={uiText("직접 작성")} /><CharacterManagementMetric label={uiText("자율활동")} value={uiText("사용하지 않음")} /></> : <>
      <CharacterManagementMetric label={uiText("활동 시간")} value={item.settings ? `${item.settings.active_hours_start}–${item.settings.active_hours_end} · ${zone}` : uiText("정보 없음")} />
      <CharacterManagementMetric label={uiText("다음 활동")} value={item.next_activity_at ? formatDate(item.next_activity_at, zone) : uiText(item.autonomous_enabled ? "예정 없음" : "자율활동 꺼짐")} />
      <div className={cardStyles.recentActivity} data-character-recent-activity={recent ? "available" : "empty"}>
        <span className={cardStyles.recentActivityEyebrow}>{uiText("최근 결과")}</span>
        <div className={cardStyles.recentActivitySummary}><Activity aria-hidden="true" className={cardStyles.recentActivityIcon} size={20} /><div className={cardStyles.recentActivityCopy}>
          <span className={cardStyles.recentActivityLabel}>{uiText(recent?.action_type === "post" ? "게시글 작성" : recent?.action_type === "reply" ? "답글 작성" : recent?.action_type === "like" ? "좋아요" : "기록 없음")}</span>
          <strong className={cardStyles.recentActivityHeadline}>{recent?.title ?? uiText("아직 활동 기록이 없어요.")}</strong>
        </div></div>
        <div className={cardStyles.recentActivityMeta}>{recent ? <time className={cardStyles.recentActivityTime} dateTime={recent.occurred_at}>{formatDate(recent.occurred_at, zone)}</time> : null}
          {recent?.post_id ? <LocalProductLink ariaLabel={uiText("게시글 보기")} className={cardStyles.recentActivityLink} href={worldPostDetailRoute(profile.world_id, recent.post_id)}><span>{uiText("게시글 보기")}</span><ChevronRight aria-hidden="true" size={16} /></LocalProductLink> : null}
        </div>
      </div>
    </>}
    policy={!isUser && item.settings ? uiText("World 활동 정책", { minutes: formatNumber(item.settings.activity_interval_minutes), posts: formatNumber(item.settings.max_posts_per_day), replies: formatNumber(item.settings.max_comments_per_day) }) : null}
  />;
}

export function worldCharacterOperationError(reason: unknown) {
  if (reason instanceof ApiRequestError) {
    if (reason.status === 409) return "World 설정이 변경되었어요. 최신 상태를 확인한 뒤 다시 저장해주세요.";
    if (reason.status === 403 || reason.status === 404) return "이 World 캐릭터를 관리할 수 없어요.";
    if (reason.status === 422) return "입력한 World 설정을 확인해주세요.";
  }
  return "World 캐릭터 작업을 완료하지 못했어요. 잠시 후 다시 시도해주세요.";
}

function preserveDirectoryAnchor(root: HTMLElement | null) {
  const owner = root?.closest<HTMLElement>('[data-device-scroll-owner="true"]');
  const anchor = root && owner ? Array.from(root.querySelectorAll<HTMLElement>('[data-world-character-id]')).find((row) => row.getBoundingClientRect().bottom > owner.getBoundingClientRect().top) : null;
  const previousTop = anchor?.getBoundingClientRect().top;
  return () => { if (anchor?.isConnected && owner && previousTop !== undefined) owner.scrollTop += anchor.getBoundingClientRect().top - previousTop; };
}

export function ProfileStatus({ title }: { title: string }) {
  const uiText = useUiText("characters");
  return (
    <section aria-live="polite" className={styles.status} role="status">
      <Users aria-hidden="true" size={27} />
      <h2>{title}</h2>
      <p>{uiText("현재 World의 identity와 capability를 확인하고 있어요.")}</p>
    </section>
  );
}

export function ProfileError({
  error,
  onRetry,
}: {
  error: Error | null;
  onRetry: () => void;
}) {
  const uiText = useUiText("characters");
  const unavailable =
    (error instanceof WorldCharacterProfileApiError || error instanceof ApiRequestError) && [401, 403, 404].includes(error.status);
  return (
    <section className={styles.status} role="alert">
      <Users aria-hidden="true" size={27} />
      <h2>{unavailable ? uiText("이 프로필을 열 수 없어요") : uiText("프로필을 불러오지 못했어요")}</h2>
      <p>
        {unavailable
          ? uiText("다른 World, 떠난 Character 또는 허용되지 않은 identity로 이동하지 않습니다.")
          : uiText("로컬 runtime 상태를 확인한 뒤 다시 시도해주세요.")}
      </p>
      {!unavailable ? (
        <button onClick={onRetry} type="button">
          <RotateCcw aria-hidden="true" size={17} />
          {uiText("다시 시도")}</button>
      ) : null}
    </section>
  );
}
