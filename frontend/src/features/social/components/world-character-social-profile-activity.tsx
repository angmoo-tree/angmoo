"use client";
import { useUiText } from "@/hooks/use-ui-text";
import { useUiDateFormatter } from "@/hooks/use-ui-date-formatter";


import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { worldCharacterProfileRoute, worldPostDetailRoute } from "@/lib/navigation/product-routes";

import { getWorldCharacterSocialProfile, WorldCharacterSocialProfileApiError } from "@/features/social/api/world-character-social-profile-client";
import type { WorldCharacterSocialProfileCounts, WorldCharacterSocialProfilePost, WorldCharacterSocialProfileTab } from "@/features/social/types/world-character-social-profile-contract";
import type { SocialPostActionPresentation, SocialPostPresentation } from "@/features/social/types/social-presentation-contract";
import { SocialPostRow } from "@/features/social/components/social-post-row";
import { useOwnerReactions } from "../hooks/use-owner-reactions";
import { useUiNumberFormatter } from "@/hooks/use-ui-number-formatter";
import styles from "./world-character-social-profile-activity.module.css";

type Props = {
  activeTab: WorldCharacterSocialProfileTab;
  onTabChange: (tab: WorldCharacterSocialProfileTab) => void;
  worldCharacterId: string;
  worldId: string;
};

type ActivityState =
  | { status: "loading" }
  | {
      status: "ready";
      counts: WorldCharacterSocialProfileCounts;
      items: WorldCharacterSocialProfilePost[];
      nextCursor: string | null;
    }
  | { status: "error"; error: Error };

const TABS: ReadonlyArray<{
  label: string;
  value: WorldCharacterSocialProfileTab;
}> = [
  { label: "지저귐", value: "posts" },
  { label: "대꾸", value: "replies" },
  { label: "좋아요", value: "likes" },
];

export function WorldCharacterSocialProfileActivity({
  activeTab,
  onTabChange,
  worldCharacterId,
  worldId,
}: Props) {
  const uiText = useUiText("social");
  const formatDate = useUiDateFormatter();
  const [state, setState] = useState<ActivityState>({ status: "loading" });
  const [loadingMore, setLoadingMore] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const requestGeneration = useRef(0);
  const reactions = useOwnerReactions(`${worldId}:${worldCharacterId}:${activeTab}`, () => setAttempt(value => value + 1), worldId);
  const formatNumber = useUiNumberFormatter();

  useEffect(() => {
    const generation = ++requestGeneration.current;
    const controller = new AbortController();
    const startTimer = window.setTimeout(() => {
      setState({ status: "loading" });
      void getWorldCharacterSocialProfile(worldId, worldCharacterId, activeTab, {
        signal: controller.signal,
      })
        .then((read) => {
          if (controller.signal.aborted || generation !== requestGeneration.current) return;
          setState({
            status: "ready",
            counts: read.counts,
            items: read.items,
            nextCursor: read.next_cursor,
          });
        })
        .catch((reason: unknown) => {
          if (reason instanceof DOMException && reason.name === "AbortError") return;
          if (controller.signal.aborted || generation !== requestGeneration.current) return;
          setState({
            status: "error",
            error:
              reason instanceof Error
                ? reason
                : new Error("world_character_social_profile_unavailable"),
          });
        });
    }, 0);
    return () => {
      window.clearTimeout(startTimer);
      requestGeneration.current += 1;
      controller.abort();
    };
  }, [activeTab, attempt, worldCharacterId, worldId]);

  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  const counts = state.status === "ready" ? state.counts : null;
  const metrics = [
      [uiText("지저귐"), counts?.post_count],
      [uiText("대꾸"), counts?.reply_count],
      [uiText("좋아요"), counts?.liked_post_count],
      [uiText("받은 좋아요"), counts?.received_like_count],
    ] as const;

  async function loadMore() {
    if (state.status !== "ready" || !state.nextCursor || loadingMore) return;
    const generation = requestGeneration.current;
    setLoadingMore(true);
    try {
      const read = await getWorldCharacterSocialProfile(
        worldId,
        worldCharacterId,
        activeTab,
        { cursor: state.nextCursor },
      );
      if (generation !== requestGeneration.current) return;
      setState((current) =>
        current.status === "ready"
          ? {
              ...current,
              counts: read.counts,
              items: [...current.items, ...read.items],
              nextCursor: read.next_cursor,
            }
          : current,
      );
    } catch (reason) {
      if (generation !== requestGeneration.current) return;
      setState({
        status: "error",
        error:
          reason instanceof Error
            ? reason
            : new Error("world_character_social_profile_unavailable"),
      });
    } finally {
      if (generation === requestGeneration.current) setLoadingMore(false);
    }
  }

  return (
    <section
      aria-label={uiText("현재 World 활동")}
      className={styles.activity}
      data-world-character-social-activity
      data-world-character-social-tab={activeTab}
    >
      <dl className={styles.metrics}>
        {metrics.map(([label, value]) => (
          <div className={styles.metric} key={label}>
            <dt>{label}</dt>
            <dd>{value == null ? "—" : formatNumber(value)}</dd>
          </div>
        ))}
      </dl>

      <div aria-label={uiText("현재 World 활동 종류")} className={styles.tabs} role="tablist">
        {TABS.map((tab) => (
          <button
            aria-controls="world-character-social-panel"
            aria-selected={activeTab === tab.value}
            className={styles.tab}
            id={`world-character-social-tab-${tab.value}`}
            key={tab.value}
            onClick={() => onTabChange(tab.value)}
            role="tab"
            tabIndex={activeTab === tab.value ? 0 : -1}
            type="button"
          >
            {uiText(tab.label)}
          </button>
        ))}
      </div>

      <div
        aria-labelledby={`world-character-social-tab-${activeTab}`}
        className={styles.panel}
        id="world-character-social-panel"
        role="tabpanel"
      >
        {reactions.error ? <p role="alert">{uiText("좋아요를 저장하지 못했습니다. 다시 시도해 주세요.")}</p> : null}
        {state.status === "loading" ? <ActivityLoading /> : null}
        {state.status === "error" ? (
          <ActivityError error={state.error} onRetry={retry} />
        ) : null}
        {state.status === "ready" && state.items.length === 0 ? (
          <div className={styles.empty}>
            <strong>{uiText(emptyTitle(activeTab))}</strong>
            <span>{uiText("현재 World에서 공개되고 확인 가능한 활동만 표시합니다.")}</span>
          </div>
        ) : null}
        {state.status === "ready" && state.items.length > 0 ? (
          <div className={styles.stream} data-social-stream="world-character-profile">
            {state.items.map((post) => {
              const detailHref = worldPostDetailRoute(worldId, post.id);
              return (
                <SocialPostRow
                  actions={[activityActions(post, detailHref)[0], reactions.likeAction(post)]}
                  onAction={() => void reactions.setReaction(post)}
                  authorHref={
                    post.author_profile_capability === "available"
                      ? worldCharacterProfileRoute(
                          worldId,
                          post.author_world_character_id,
                        )
                      : undefined
                  }
                  context={
                    activeTab === "replies"
                      ? uiText("이 World에서 남긴 대꾸")
                      : activeTab === "likes"
                        ? uiText("이 World에서 좋아요한 글")
                        : undefined
                  }
                  href={detailHref}
                  key={`${activeTab}:${post.id}`}
                  post={presentActivityPost(post, formatDate)}
                  variant={post.reply_to_post_id ? "reply" : "feed"}
                />
              );
            })}
          </div>
        ) : null}
        {state.status === "ready" && state.nextCursor ? (
          <div className={styles.moreRow}>
            <button disabled={loadingMore} onClick={() => void loadMore()} type="button">
              <RefreshCw aria-hidden="true" className={loadingMore ? styles.spin : undefined} size={17} />
              {loadingMore ? uiText("불러오는 중") : uiText("더 보기")}
            </button>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function presentActivityPost(
  post: WorldCharacterSocialProfilePost,
  formatDate: (value: string) => string,
): SocialPostPresentation {
  return {
    id: post.id,
    authorAvatarUrl: post.author_avatar_url,
    authorHandle: post.author_handle,
    authorName: post.author_name,
    authorDeleted: post.author_deleted,
    createdAt: post.created_at,
    timeLabel: formatDate(post.created_at),
    title: post.reply_to_post_id ? "" : post.title,
    body: post.body,
    media: post.media,
    mentionedCharacters: post.mentioned_characters,
  };
}

function activityActions(
  post: WorldCharacterSocialProfilePost,
  detailHref: string,
): SocialPostActionPresentation[] {
  return [
    {
      kind: "reply",
      interaction: "link",
      label: "대꾸",
      count: post.reply_count,
      href: detailHref,
    },
    {
      kind: "like",
      interaction: "metric",
      label: "좋아요",
      count: post.like_count,
    },
  ];
}

function ActivityLoading() {
  const uiText = useUiText("social");
  return (
    <div aria-live="polite" className={styles.loading} role="status">
      <span>{uiText("현재 World 활동을 불러오는 중")}</span>
      <i aria-hidden="true" />
      <i aria-hidden="true" />
    </div>
  );
}

function ActivityError({ error, onRetry }: { error: Error; onRetry: () => void }) {
  const uiText = useUiText("social");
  const unavailable =
    error instanceof WorldCharacterSocialProfileApiError &&
    (error.status === 403 || error.status === 404);
  return (
    <div className={styles.error} role="alert">
      <strong>{unavailable ? uiText("이 활동을 볼 수 없어요") : uiText("활동을 불러오지 못했어요")}</strong>
      <span>
        {unavailable
          ? uiText("현재 World의 참여·차단 상태를 확인해 주세요.")
          : uiText("로컬 runtime 상태를 확인한 뒤 다시 시도해 주세요.")}
      </span>
      {!unavailable ? (
        <button onClick={onRetry} type="button">
          <RefreshCw aria-hidden="true" size={17} />
          {uiText("다시 시도")}</button>
      ) : null}
    </div>
  );
}

function emptyTitle(tab: WorldCharacterSocialProfileTab) {
  if (tab === "replies") return "아직 공개된 대꾸가 없어요";
  if (tab === "likes") return "아직 좋아요한 글이 없어요";
  return "아직 공개된 지저귐이 없어요";
}
