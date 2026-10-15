"use client";
import { ArrowLeft, Bell, Check, RefreshCw } from "lucide-react";
import { useUiText } from "@/hooks/use-ui-text";
import { LocalProductLink } from "@/components/navigation/local-product-link";
import { Button } from "@/components/ui/button";
import { CountBadge } from "@/components/ui/count-badge";
import { worldNotificationsRoute, worldFeedRoute, worldPostDetailRoute, worldCharacterProfileRoute, studioWorldRoute } from "@/lib/navigation/product-routes";
import { useWorldNotificationView } from "../hooks/world-notification-context";
import { NotificationList } from "./notification-list";
import styles from "./world-notifications.module.css";

export function WorldNotificationBell({ worldId }: { worldId: string }) {
  const text = useUiText("social");
  const { state } = useWorldNotificationView();
  const label = state.unreadCount === null ? text("알림 수를 확인하고 있어요.") : text("알림, 읽지 않은 알림 {{count}}개", { count: state.unreadCount });
  const description = state.error && state.unreadCount === null ? text("알림 수를 확인하지 못했어요.")
    : state.error || state.stale ? text("알림 수를 갱신하지 못했어요. 이전 수를 표시해요.") : label;
  return <LocalProductLink href={worldNotificationsRoute(worldId)} className={styles.bell} ariaLabel={state.unreadCount === null && state.error ? text("알림 수를 확인하지 못했어요.") : state.stale ? `${label} ${text("이전에 확인한 수예요.")}` : label}
    title={description} data-notification-count-state={state.stale ? "stale" : state.unreadCount === null ? state.error ? "unavailable" : "unknown" : "current"}>
    <Bell size={23} aria-hidden="true" /><CountBadge count={state.unreadCount} stale={state.stale} />
  </LocalProductLink>;
}

export function WorldNotifications({ worldId }: { worldId: string }) {
  const text = useUiText("social");
  const { state, controller, scope } = useWorldNotificationView();
  const labels: Record<string, string> = { reply: "{{actor}}님이 내 글에 답글을 남겼어요.", like: "{{actor}}님이 내 글을 좋아했어요.", quote: "{{actor}}님이 내 글을 인용했어요.",
    mention: "{{actor}}님이 나를 멘션했어요.", repost: "{{actor}}님이 내 글을 리포스트했어요.", follow: "{{actor}}님이 나를 팔로우했어요." };
  const items = state.items.map(item => {
    const name = item.actor_name ?? text("삭제한 캐릭터");
    const href = !item.target.can_open ? null : item.target.kind === "post" && item.target.post_id ? worldPostDetailRoute(worldId, item.target.post_id)
      : item.target.world_character_id ? worldCharacterProfileRoute(worldId, item.target.world_character_id) : null;
    return { id: item.id, type: item.notification_type, actorName: name, actorAvatar: item.actor_avatar_url,
      actorHandle: item.actor_handle, actorHref: item.actor_world_character_id ? worldCharacterProfileRoute(worldId, item.actor_world_character_id) : null,
      href, title: text(labels[item.notification_type], { actor: name }), body: item.preview_text, readAt: item.read_at, createdAt: item.created_at };
  });
  return <section className={styles.page} data-world-notifications>
    <header className={styles.header}><LocalProductLink className={styles.control} href={worldFeedRoute(worldId)} ariaLabel={text("피드로 돌아가기")}><ArrowLeft size={21} aria-hidden="true" /></LocalProductLink>
      <h1>{text("알림")}</h1><button type="button" className={styles.control} aria-label={text("모두 읽음으로 표시")} title={text("모두 읽음으로 표시")}
        aria-busy={state.readAllPending} disabled={!scope || state.unreadCount === null || state.unreadCount === 0 || state.readAllPending}
        onClick={() => void controller?.markAllRead()}><Check size={20} aria-hidden="true" /></button>
      <button type="button" className={styles.control} aria-label={text("새로고침")} disabled={state.loading} onClick={() => void controller?.refresh()}><RefreshCw size={20} aria-hidden="true" /></button></header>
    {!scope ? <p className={styles.message}><LocalProductLink href={studioWorldRoute(worldId)}>{text("World 관리에서 내 프로필을 확인해 주세요.")}</LocalProductLink></p> : null}
    {state.error ? <div className={styles.errorPanel} role="status"><p className={styles.error}>{text("알림을 불러오지 못했어요. 다시 시도해 주세요.")}</p><Button compact variant="secondary" onClick={() => void controller?.refresh()}>{text("다시 시도")}</Button></div> : null}
    {state.readAllPending || state.readAllStatus !== "idle" ? <div className={styles.message} role="status" data-read-all-status={state.readAllPending ? "pending" : state.readAllStatus}>
      {state.readAllPending ? text("읽음 처리 중이에요.") : state.readAllStatus === "success" ? text("알림을 모두 읽음으로 표시했어요.")
        : state.readAllStatus === "failed" ? text("알림을 읽음으로 표시하지 못했어요. 다시 시도해 주세요.")
          : text("읽음 처리 결과를 확인하지 못했어요. 다시 확인해 주세요.")}
      {state.readAllStatus === "uncertain" && !state.readAllPending ? <Button compact variant="secondary" onClick={() => void controller?.refresh()}>{text("다시 확인")}</Button> : null}
    </div> : null}
    {scope && state.unreadCount === null && !state.error ? <p className={styles.message}>{text("알림을 불러오는 중")}</p> : null}
    {scope && state.unreadCount !== null && !state.loading && !state.items.length && !state.error ? <p className={styles.message}>{text("아직 받은 알림이 없어요.")}</p> : null}
    <NotificationList items={items} readMode="bulk" />
    {state.nextCursor ? <div className={styles.more}><Button compact variant="secondary" disabled={state.loadingMore} onClick={() => void controller?.loadMore()}>{text("더 보기")}</Button></div> : null}
  </section>;
}
