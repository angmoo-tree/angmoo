"use client";
import { AtSign, Bell, Check, Heart, MessageCircle, Quote, Repeat2, UserPlus } from "lucide-react";
import { useUiText } from "@/hooks/use-ui-text";
import { useUiDateFormatter } from "@/hooks/use-ui-date-formatter";
import { LocalProductLink } from "@/components/navigation/local-product-link";
import { ProfileAvatar } from "@/components/ui/profile-avatar";
import styles from "./world-notifications.module.css";

export type NotificationListItem = { id: number; type: string; actorName: string; actorHandle: string | null;
  actorAvatar: string | null; actorHref: string | null; href: string | null; title: string; body: string | null;
  readAt: string | null; createdAt: string };
const TYPES: Record<string, string> = { reply: "답글", quote: "인용", mention: "멘션", like: "좋아요", repost: "리포스트", follow: "팔로우" };
const ICONS = { reply: MessageCircle, quote: Quote, mention: AtSign, like: Heart, repost: Repeat2, follow: UserPlus };

type NotificationListProps = { items: NotificationListItem[] } & ({ readMode: "bulk" } |
  { readMode?: "individual"; reading: ReadonlySet<number>; errors: ReadonlySet<number>; onRead: (id: number) => void });

/** Shared list anatomy; World read state is a marker, global reads stay explicit. */
export function NotificationList(props: NotificationListProps) {
  const { items } = props;
  const text = useUiText("social"), formatDate = useUiDateFormatter();
  return <div className={styles.list}>{items.map(item => {
    const Icon = ICONS[item.type as keyof typeof ICONS] ?? Bell;
    const avatar = <ProfileAvatar name={item.actorName} avatarUrl={item.actorAvatar} sizeClassName="size-12" textClassName="text-[20px]" />;
    return <article key={item.id} className={styles.item} data-world-notification={item.id}>
      {item.actorHref ? <LocalProductLink className={styles.actor} href={item.actorHref} ariaLabel={item.actorName}>{avatar}</LocalProductLink> : avatar}
      <div className={styles.content}>
        <div className={styles.meta}><span className={styles.type}><Icon size={15} aria-hidden="true" />{text(TYPES[item.type] ?? "알림")}</span>
          <time dateTime={item.createdAt}>{formatDate(item.createdAt)}</time>{props.readMode === "bulk" ? !item.readAt ?
            <span className={styles.unread} data-notification-unread><span className={styles.unreadDot} aria-hidden="true" />{text("미읽음")}</span> : null
            : item.readAt ? <span>{text("읽음")}</span> : null}</div>
        {item.href ? <LocalProductLink className={styles.target} href={item.href}><strong>{item.title}</strong></LocalProductLink> : <strong>{item.title}</strong>}
        {item.actorHandle ? <span className={styles.handle}>@{item.actorHandle}</span> : null}
        {item.body ? item.href ? <LocalProductLink className={styles.preview} href={item.href}>{item.body}</LocalProductLink> : <p className={styles.preview}>{item.body}</p> : null}
        {props.readMode !== "bulk" && props.errors.has(item.id) ? <p className={styles.error} role="status">{text("읽음 상태를 저장하지 못했어요. 다시 시도해 주세요.")}</p> : null}
      </div>
      {props.readMode !== "bulk" && !item.readAt ? <button className={styles.control} type="button" aria-label={text("읽음으로 표시")} title={text("읽음으로 표시")}
        aria-busy={props.reading.has(item.id)} disabled={props.reading.has(item.id)} onClick={() => props.onRead(item.id)}><Check size={20} aria-hidden="true" /></button> : null}
    </article>;
  })}</div>;
}
