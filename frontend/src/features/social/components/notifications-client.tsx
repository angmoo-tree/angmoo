"use client";
import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useUiText } from "@/hooks/use-ui-text";
import { Button } from "@/components/ui/button";
import { captureAuthRequestScope, isCurrentAuthRequestScope } from "@/lib/auth/browser-session";
import { listNotifications, markNotificationRead } from "../api/community";
import type { NotificationRead } from "../types/community";
import { NotificationList } from "./notification-list";
import { notificationActorHref, notificationCopy } from "./legacy-notification-presentation";
import styles from "./world-notifications.module.css";

/** Compatibility controller; World reads use their separate, narrower API. */
export function NotificationsClient() {
  const text = useUiText("social");
  const [items, setItems] = useState<NotificationRead[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(false);
  const [reading, setReading] = useState<ReadonlySet<number>>(new Set());
  const [readErrors, setReadErrors] = useState<ReadonlySet<number>>(new Set());
  const generation = useRef(0);
  const inFlight = useRef(false);
  const load = useCallback(async (append = false, next?: string | null) => {
    if (inFlight.current) return;
    inFlight.current = true;
    const admission = captureAuthRequestScope(), sequence = ++generation.current;
    if (append) setLoadingMore(true); else setLoading(true);
    setError(false);
    try {
      const page = await listNotifications({ limit: 10, cursor: append ? next : null });
      if (sequence !== generation.current || !isCurrentAuthRequestScope(admission)) return;
      setItems(previous => append ? [...previous, ...page.items.filter(item => !previous.some(old => old.id === item.id))] : page.items);
      setCursor(page.next_cursor);
    } catch { if (sequence === generation.current && isCurrentAuthRequestScope(admission)) setError(true); }
    finally { inFlight.current = false; if (sequence === generation.current) { setLoading(false); setLoadingMore(false); } }
  }, []);
  const invalidate = useCallback(() => { generation.current++; }, []);
  useEffect(() => {
    let active = true;
    queueMicrotask(() => { if (active) void load(); });
    return () => { active = false; invalidate(); };
  }, [load, invalidate]);
  useEffect(() => {
    if (!cursor || loadingMore || loading) return;
    const scroll = () => {
      if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 520) void load(true, cursor);
    };
    window.addEventListener("scroll", scroll, { passive: true });
    return () => window.removeEventListener("scroll", scroll);
  }, [cursor, loadingMore, loading, load]);
  const read = async (id: number) => {
    if (reading.has(id)) return;
    const admission = captureAuthRequestScope();
    setReading(previous => new Set([...previous, id]));
    try {
      const updated = await markNotificationRead(id);
      if (!isCurrentAuthRequestScope(admission)) return;
      setItems(previous => previous.map(item => item.id === id ? updated : item));
      setReadErrors(previous => new Set([...previous].filter(value => value !== id)));
    } catch { if (isCurrentAuthRequestScope(admission)) setReadErrors(previous => new Set([...previous, id])); }
    finally { setReading(previous => new Set([...previous].filter(value => value !== id))); }
  };
  const rows = items.map(item => {
    const copy = notificationCopy(item, text);
    return { id: item.id, type: item.notification_type, actorName: item.actor_deleted ? text("삭제한 캐릭터") : item.actor_name ?? text("알림"),
      actorAvatar: item.actor_avatar_url, actorHandle: item.actor_handle, actorHref: item.actor_deleted ? null : notificationActorHref(item),
      href: copy.href, title: copy.title, body: copy.body, readAt: item.read_at, createdAt: item.created_at };
  });
  return <section className={styles.page}>
    <header className={styles.header}><h1>{text("알림")}</h1><button type="button" className={styles.control} disabled={loading} aria-label={text("새로고침")} onClick={() => void load()}><RefreshCw size={20} aria-hidden="true" /></button></header>
    {error ? <p className={styles.errorPanel} role="status">{text("알림을 불러오지 못했어요. 다시 시도해 주세요.")}</p> : null}
    {loading ? <p className={styles.message}>{text("알림을 불러오는 중")}</p> : null}
    {!loading && !error && !items.length ? <p className={styles.message}>{text("아직 알림이 없습니다.")}</p> : null}
    <NotificationList items={rows} reading={reading} errors={readErrors} onRead={id => void read(id)} />
    {cursor ? <div className={styles.more}><Button compact variant="secondary" disabled={loadingMore} onClick={() => void load(true, cursor)}>{text("더 보기")}</Button></div> : null}
  </section>;
}
