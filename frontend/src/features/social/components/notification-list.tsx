"use client";
import { AtSign, Bell, Check, Heart, MessageCircle, Quote, Repeat2, UserPlus } from "lucide-react";
import { useUiText } from "@/hooks/use-ui-text";
import { useUiDateFormatter } from "@/hooks/use-ui-date-formatter";
import { LocalProductLink } from "@/components/navigation/local-product-link";
import { ProfileAvatar } from "@/components/ui/profile-avatar";
import type { NotificationScope } from "../types/world-notifications";
import styles from "./world-notifications.module.css";

export type NotificationListItem = { id: number; type: string; actorName: string; actorHandle: string | null;
  actorAvatar: string | null; actorHref: string | null; href: string | null; title: string; body: string | null;
  readAt: string | null; createdAt: string };
const TYPES: Record<string, string> = { reply: "답글", quote: "인용", mention: "멘션", like: "좋아요", repost: "리포스트", follow: "팔로우" };
const ICONS = { reply: MessageCircle, quote: Quote, mention: AtSign, like: Heart, repost: Repeat2, follow: UserPlus };

/** Existing avatar, reaction chip, time, preview and individual check anatomy. */
export function NotificationList({ items, reading, errors, onRead, scope }: { items: NotificationListItem[];
  reading: ReadonlySet<number>; errors: ReadonlySet<number>; onRead: (id: number) => void; scope?: NotificationScope | null }) {
  const text = useUiText("social"), formatDate = useUiDateFormatter();
  return <div className={styles.list}>{items.map(item => {
    const Icon = ICONS[item.type as keyof typeof ICONS] ?? Bell;
    const attributes = scope ? { "data-notification-id": item.id, "data-notification-world": scope.world_id, "data-notification-profile": scope.recipient_world_character_id } : {};
    const avatar = <ProfileAvatar name={item.actorName} avatarUrl={item.actorAvatar} sizeClassName="size-12" textClassName="text-[20px]" />;
    return <article key={item.id} className={styles.item} data-world-notification={item.id}>
      {item.actorHref ? <LocalProductLink className={styles.actor} href={item.actorHref} ariaLabel={item.actorName}>{avatar}</LocalProductLink> : avatar}
      <div className={styles.content}>
        <div className={styles.meta}><span className={styles.type}><Icon size={15} aria-hidden="true" />{text(TYPES[item.type] ?? "알림")}</span>
          <time dateTime={item.createdAt}>{formatDate(item.createdAt)}</time>{item.readAt ? <span>{text("읽음")}</span> : null}</div>
        {item.href ? <LocalProductLink {...attributes} className={styles.target} href={item.href}><strong>{item.title}</strong></LocalProductLink> : <strong>{item.title}</strong>}
        {item.actorHandle ? <span className={styles.handle}>@{item.actorHandle}</span> : null}
        {item.body ? item.href ? <LocalProductLink {...attributes} className={styles.preview} href={item.href}>{item.body}</LocalProductLink> : <p className={styles.preview}>{item.body}</p> : null}
        {errors.has(item.id) ? <p className={styles.error} role="status">{text("읽음 상태를 저장하지 못했어요. 다시 시도해 주세요.")}</p> : null}
      </div>
      {!item.readAt ? <button className={styles.control} type="button" aria-label={text("읽음으로 표시")} title={text("읽음으로 표시")}
        aria-busy={reading.has(item.id)} disabled={reading.has(item.id)} onClick={() => onRead(item.id)}><Check size={20} aria-hidden="true" /></button> : null}
    </article>;
  })}</div>;
}
