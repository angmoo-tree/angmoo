"use client";

import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { useUiText } from "@/hooks/use-ui-text";
import { useUiDateFormatter } from "@/hooks/use-ui-date-formatter";
import { useUiNumberFormatter } from "@/hooks/use-ui-number-formatter";
import { AUTH_CHANGED_EVENT, captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT } from "@/lib/runtime/runtime-config";
import { worldCharacterProfileRoute, worldPostDetailRoute } from "@/lib/navigation/product-routes";
import { getWorldCharacterSocialProfile, WorldCharacterSocialProfileApiError } from "../api/world-character-social-profile-client";
import type { WorldCharacterSocialProfileCounts, WorldCharacterSocialProfilePost, WorldCharacterSocialProfileTab } from "../types/world-character-social-profile-contract";
import type { SocialPostPresentation } from "../types/social-presentation-contract";
import { SocialPostRow } from "./social-post-row";
import { ProfileStatistics } from "@/components/content/profile-statistics";
import { useOwnerReactions } from "../hooks/use-owner-reactions";
import { applyConfirmedReaction } from "../utils/confirmed-reactions";
import { captureActivityAnchor } from "../utils/activity-scroll-anchor";
import styles from "./world-character-social-profile-activity.module.css";

type Props = {
  activeTab: WorldCharacterSocialProfileTab;
  onTabChange: (tab: WorldCharacterSocialProfileTab) => void;
  worldCharacterId: string;
  worldId: string;
  renderProfile?: (metrics: ReactNode) => ReactNode;
};
type ReadyActivity = { key: string; status: "ready"; counts: WorldCharacterSocialProfileCounts; items: WorldCharacterSocialProfilePost[]; nextCursor: string | null };
type ActivityState = { key: string; status: "loading" } | ReadyActivity | { key: string; status: "error"; error: Error };
const TABS = [{ label: "지저귐", value: "posts" }, { label: "대꾸", value: "replies" }, { label: "좋아요", value: "likes" }] as const;

function uniquePosts(items: WorldCharacterSocialProfilePost[]) {
  return [...new Map(items.map(post => [post.id, post])).values()];
}
function asError(reason: unknown) { return reason instanceof Error ? reason : new Error("world_character_social_profile_unavailable"); }
function unavailable(reason: unknown) { return reason instanceof WorldCharacterSocialProfileApiError && [401, 403, 404].includes(reason.status); }

export function WorldCharacterSocialProfileActivity({ activeTab, onTabChange, worldCharacterId, worldId, renderProfile }: Props) {
  const uiText = useUiText("social"), formatDate = useUiDateFormatter(), formatNumber = useUiNumberFormatter();
  const routeKey = JSON.stringify([worldId, worldCharacterId, activeTab]);
  const [state, setState] = useState<ActivityState>({ key: routeKey, status: "loading" });
  const [loadingMore, setLoadingMore] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [refreshEpoch, setRefreshEpoch] = useState(0);
  const [backgroundError, setBackgroundError] = useState<{ key: string; error: Error } | null>(null);
  const requestGeneration = useRef(0), backgroundGeneration = useRef(0);
  const stateRef = useRef(state);
  const loadedPages = useRef(1), loadingMoreRef = useRef(false), refreshRequested = useRef(false);
  const container = useRef<HTMLElement | null>(null);
  const restoreAnchor = useRef<(() => void) | null>(null);
  const current: ActivityState = state.key === routeKey ? state : { key: routeKey, status: "loading" };
  useEffect(() => { stateRef.current = state; }, [state]);
  useLayoutEffect(() => { restoreAnchor.current?.(); restoreAnchor.current = null; }, [state]);

  const reactions = useOwnerReactions(routeKey, change => {
    setState(previous => previous.key === routeKey && previous.status === "ready"
      ? { ...previous, items: previous.items.map(post => applyConfirmedReaction(post, change)) } : previous);
    // Counts and likes membership are server facts. Coalesce their background
    // reads, keeping existing rows mounted until the canonical page chain arrives.
    refreshRequested.current = true;
    setRefreshEpoch(value => value + 1);
  }, worldId);
  const { captureReadRevision, reconcilePost } = reactions;

  useEffect(() => {
    const generation = ++requestGeneration.current;
    const background = ++backgroundGeneration.current;
    const authScope = captureAuthRequestScope(), controller = new AbortController();
    const readRevision = captureReadRevision();
    loadedPages.current = 1; loadingMoreRef.current = false; refreshRequested.current = false;
    const start = window.setTimeout(() => {
      setState({ key: routeKey, status: "loading" }); setLoadingMore(false); setBackgroundError(null);
      void getWorldCharacterSocialProfile(worldId, worldCharacterId, activeTab, { signal: controller.signal }).then(read => {
        if (controller.signal.aborted || generation !== requestGeneration.current || !isCurrentAuthRequestScope(authScope)) return;
        setState({ key: routeKey, status: "ready", counts: read.counts,
          items: read.items.map(post => reconcilePost(post, readRevision)), nextCursor: read.next_cursor });
        if (readRevision !== captureReadRevision()) { refreshRequested.current = true; setRefreshEpoch(value => value + 1); }
      }).catch(reason => {
        if (controller.signal.aborted || generation !== requestGeneration.current || !isCurrentAuthRequestScope(authScope)) return;
        setState({ key: routeKey, status: "error", error: asError(reason) });
      });
    }, 0);
    const changed = () => {
      if (!isCurrentAuthRequestScope(authScope)) { ++requestGeneration.current; controller.abort(); setAttempt(value => value + 1); }
    };
    window.addEventListener(AUTH_CHANGED_EVENT, changed);
    window.addEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, changed);
    return () => {
      window.clearTimeout(start); requestGeneration.current = generation + 1; backgroundGeneration.current = background + 1; controller.abort();
      window.removeEventListener(AUTH_CHANGED_EVENT, changed);
      window.removeEventListener(DESKTOP_RUNTIME_CONFIG_CHANGED_EVENT, changed);
    };
  }, [activeTab, attempt, worldCharacterId, worldId, routeKey, captureReadRevision, reconcilePost]);

  useEffect(() => {
    const existing = stateRef.current;
    if (!refreshRequested.current || loadingMoreRef.current || existing.key !== routeKey || existing.status !== "ready") return;
    const generation = requestGeneration.current, background = ++backgroundGeneration.current;
    const authScope = captureAuthRequestScope(), readRevision = captureReadRevision(), controller = new AbortController();
    const pages = loadedPages.current;
    const start = window.setTimeout(() => {
      refreshRequested.current = false;
      void (async () => {
        try {
          let cursor: string | null = null;
          let items: WorldCharacterSocialProfilePost[] = [], counts = existing.counts;
          const seen = new Set<string>();
          for (let page = 0; page < pages; page++) {
            const read = await getWorldCharacterSocialProfile(worldId, worldCharacterId, activeTab, { cursor, signal: controller.signal });
            items = [...items, ...read.items]; counts = read.counts; cursor = read.next_cursor;
            if (!cursor) break;
            if (seen.has(cursor)) throw new WorldCharacterSocialProfileApiError(502, "world_character_social_profile_cursor_cycle", true);
            seen.add(cursor);
          }
          if (controller.signal.aborted || generation !== requestGeneration.current || background !== backgroundGeneration.current || !isCurrentAuthRequestScope(authScope)) return;
          if (readRevision !== captureReadRevision()) { refreshRequested.current = true; setRefreshEpoch(value => value + 1); return; }
          items = uniquePosts(items);
          restoreAnchor.current = captureActivityAnchor(container.current, new Set(items.map(post => post.id)));
          setState({ key: routeKey, status: "ready", counts, items, nextCursor: cursor }); setBackgroundError(null);
        } catch (reason) {
          if (controller.signal.aborted || generation !== requestGeneration.current || background !== backgroundGeneration.current || !isCurrentAuthRequestScope(authScope)) return;
          if (unavailable(reason)) setState({ key: routeKey, status: "error", error: asError(reason) });
          else setBackgroundError({ key: routeKey, error: asError(reason) });
        }
      })();
    }, 0);
    return () => { window.clearTimeout(start); controller.abort(); };
  }, [refreshEpoch, routeKey, worldId, worldCharacterId, activeTab, captureReadRevision]);

  async function loadMore() {
    if (current.status !== "ready" || !current.nextCursor || loadingMoreRef.current) return;
    const generation = requestGeneration.current, authScope = captureAuthRequestScope(), readRevision = captureReadRevision();
    ++backgroundGeneration.current;
    loadingMoreRef.current = true; setLoadingMore(true);
    try {
      const read = await getWorldCharacterSocialProfile(worldId, worldCharacterId, activeTab, { cursor: current.nextCursor });
      if (generation !== requestGeneration.current || !isCurrentAuthRequestScope(authScope)) return;
      loadedPages.current += 1;
      setState(previous => previous.key === routeKey && previous.status === "ready" ? { ...previous,
        counts: readRevision === captureReadRevision() ? read.counts : previous.counts,
        items: uniquePosts([...previous.items, ...read.items.map(post => reconcilePost(post, readRevision))]), nextCursor: read.next_cursor } : previous);
      setBackgroundError(null);
    } catch (reason) {
      if (generation !== requestGeneration.current || !isCurrentAuthRequestScope(authScope)) return;
      if (unavailable(reason)) setState({ key: routeKey, status: "error", error: asError(reason) });
      else setBackgroundError({ key: routeKey, error: asError(reason) });
    } finally {
      if (generation === requestGeneration.current && isCurrentAuthRequestScope(authScope)) {
        loadingMoreRef.current = false; setLoadingMore(false);
        if (refreshRequested.current) setRefreshEpoch(value => value + 1);
      }
    }
  }
  const retry = useCallback(() => setAttempt(value => value + 1), []);
  const retryBackground = () => { refreshRequested.current = true; setRefreshEpoch(value => value + 1); };
  const counts = current.status === "ready" ? current.counts : null;
  const metrics = <ProfileStatistics data-world-social-profile-metrics statistics={[
    { label: uiText("지저귐"), value: counts?.post_count == null ? "—" : formatNumber(counts.post_count) },
    { label: uiText("대꾸"), value: counts?.reply_count == null ? "—" : formatNumber(counts.reply_count) },
    { label: uiText("좋아요"), value: counts?.liked_post_count == null ? "—" : formatNumber(counts.liked_post_count) },
    { label: uiText("받은 좋아요"), value: counts?.received_like_count == null ? "—" : formatNumber(counts.received_like_count) },
  ]} />;
  return <>
    {renderProfile ? renderProfile(metrics) : null}
    <section aria-label={uiText("현재 World 활동")} className={styles.activity} ref={container} data-world-character-social-activity data-world-character-social-tab={activeTab}>
      {!renderProfile ? metrics : null}
      <div aria-label={uiText("현재 World 활동 종류")} className={styles.tabs} role="tablist">
        {TABS.map(tab => <button aria-controls="world-character-social-panel" aria-selected={activeTab === tab.value} className={styles.tab}
          id={`world-character-social-tab-${tab.value}`} key={tab.value} onClick={() => onTabChange(tab.value)} role="tab" tabIndex={activeTab === tab.value ? 0 : -1} type="button">{uiText(tab.label)}</button>)}
      </div>
      <div aria-labelledby={`world-character-social-tab-${activeTab}`} className={styles.panel} id="world-character-social-panel" role="tabpanel">
        {reactions.error ? <p role="alert">{uiText("좋아요를 저장하지 못했습니다. 다시 시도해 주세요.")}</p> : null}
        {backgroundError?.key === routeKey ? <div className={styles.refreshError} role="alert"><span>{uiText("활동을 다시 확인하지 못했습니다. 현재 표시와 저장된 좋아요는 유지됩니다.")}</span><button type="button" onClick={retryBackground}>{uiText("다시 시도")}</button></div> : null}
        {current.status === "loading" ? <ActivityLoading /> : null}
        {current.status === "error" ? <ActivityError error={current.error} onRetry={retry} /> : null}
        {current.status === "ready" && current.items.length === 0 ? <div className={styles.empty}><strong>{uiText(emptyTitle(activeTab))}</strong><span>{uiText("현재 World에서 공개되고 확인 가능한 활동만 표시합니다.")}</span></div> : null}
        {current.status === "ready" && current.items.length > 0 ? <div className={styles.stream} data-social-stream="world-character-profile">
          {current.items.map(post => {
            const href = worldPostDetailRoute(worldId, post.id);
            return <SocialPostRow key={post.id} actions={[{ kind: "reply", interaction: "link", label: "대꾸", count: post.reply_count, href }, reactions.likeAction(post)]}
              onAction={() => void reactions.setReaction(post)} authorHref={post.author_profile_capability === "available" ? worldCharacterProfileRoute(worldId, post.author_world_character_id) : undefined}
              context={activeTab === "replies" ? uiText("이 World에서 남긴 대꾸") : activeTab === "likes" ? uiText("이 World에서 좋아요한 글") : undefined}
              href={href} post={presentActivityPost(post, formatDate)} variant={post.reply_to_post_id ? "reply" : "feed"} />;
          })}
        </div> : null}
        {current.status === "ready" && current.nextCursor ? <div className={styles.moreRow}><button disabled={loadingMore} onClick={() => void loadMore()} type="button"><RefreshCw aria-hidden="true" className={loadingMore ? styles.spin : undefined} size={17} />{loadingMore ? uiText("불러오는 중") : uiText("더 보기")}</button></div> : null}
      </div>
    </section>
  </>;
}

function presentActivityPost(post: WorldCharacterSocialProfilePost, formatDate: (value: string) => string): SocialPostPresentation {
  return { id: post.id, authorAvatarUrl: post.author_avatar_url, authorHandle: post.author_handle, authorName: post.author_name, authorDeleted: post.author_deleted,
    createdAt: post.created_at, timeLabel: formatDate(post.created_at), title: post.reply_to_post_id ? "" : post.title, body: post.body, media: post.media, mentionedCharacters: post.mentioned_characters };
}
function ActivityLoading() {
  const uiText = useUiText("social");
  return <div aria-live="polite" className={styles.loading} role="status"><span>{uiText("현재 World 활동을 불러오는 중")}</span><i aria-hidden="true" /><i aria-hidden="true" /></div>;
}
function ActivityError({ error, onRetry }: { error: Error; onRetry: () => void }) {
  const uiText = useUiText("social"), denied = unavailable(error);
  return <div className={styles.error} role="alert"><strong>{denied ? uiText("이 활동을 볼 수 없어요") : uiText("활동을 불러오지 못했어요")}</strong>
    <span>{denied ? uiText("현재 World의 참여·차단 상태를 확인해 주세요.") : uiText("로컬 runtime 상태를 확인한 뒤 다시 시도해 주세요.")}</span>
    {!denied ? <button onClick={onRetry} type="button"><RefreshCw aria-hidden="true" size={17} />{uiText("다시 시도")}</button> : null}</div>;
}
function emptyTitle(tab: WorldCharacterSocialProfileTab) {
  if (tab === "replies") return "아직 공개된 대꾸가 없어요";
  if (tab === "likes") return "아직 좋아요한 글이 없어요";
  return "아직 공개된 지저귐이 없어요";
}
