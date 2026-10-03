"use client";
import { useUiDateFormatter } from "@/hooks/use-ui-date-formatter";

import { useUiText } from "@/hooks/use-ui-text";


import { AtSign, Bell, Check, Heart, MessageCircle, Quote, RefreshCw, Repeat2, UserPlus } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ProfileAvatar } from "@/components/ui/profile-avatar";

import { listNotifications, markNotificationRead } from "@/features/social/api/community";
import { type NotificationRead } from "@/features/social/types/community";

export function NotificationsClient() {
  const formatDate = useUiDateFormatter();
  const uiText = useUiText("social");
  const [notifications, setNotifications] = useState<NotificationRead[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadNotifications = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const page = await listNotifications({ limit: 10 });
      setNotifications(page.items);
      setNextCursor(page.next_cursor);
    } catch (err) {
      setError(err instanceof Error ? uiText(err.message) : uiText("알림을 불러오지 못했습니다."));
    } finally {
      setLoading(false);
    }
  }, [uiText]);

  useEffect(() => {
    let active = true;
    listNotifications({ limit: 10 })
      .then((page) => {
        if (!active) return;
        setNotifications(page.items);
        setNextCursor(page.next_cursor);
      })
      .catch((err) => {
        if (!active) return;
        setError(err instanceof Error ? uiText(err.message) : uiText("알림을 불러오지 못했습니다."));
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [uiText]);

  const loadMore = useCallback(async () => {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    setError(null);

    try {
      const page = await listNotifications({ limit: 10, cursor: nextCursor });
      setNotifications((previous) => [...previous, ...page.items]);
      setNextCursor(page.next_cursor);
    } catch (err) {
      setError(err instanceof Error ? uiText(err.message) : uiText("알림을 더 불러오지 못했습니다."));
    } finally {
      setLoadingMore(false);
    }
  }, [loadingMore, nextCursor, uiText]);

  useEffect(() => {
    if (!nextCursor || loadingMore) return;

    function handleScroll() {
      const element = document.documentElement;
      const nearBottom = window.innerHeight + window.scrollY >= element.scrollHeight - 520;
      if (!nearBottom) return;
      void loadMore();
    }

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [loadMore, loadingMore, nextCursor]);

  async function handleRead(notificationId: number) {
    setSavingId(notificationId);
    setError(null);

    try {
      const updated = await markNotificationRead(notificationId);
      setNotifications((items) =>
        items.map((item) => (item.id === notificationId ? updated : item)),
      );
    } catch (err) {
      setError(err instanceof Error ? uiText(err.message) : uiText("알림을 읽음 처리하지 못했습니다."));
    } finally {
      setSavingId(null);
    }
  }

  return (
    <section className="min-h-screen bg-white">
      <div className="sticky top-0 z-10 flex min-h-[88px] w-full items-center gap-3 border-b border-[#eaedf2] bg-white/95 px-5 py-4 backdrop-blur-sm md:px-9">
        <h1 className="shrink-0 text-[28px] font-extrabold text-[#101828] md:text-[30px]">{uiText("알림")}</h1>
        <button
          type="button"
          onClick={loadNotifications}
          disabled={loading}
          className="ml-auto inline-flex size-11 shrink-0 items-center justify-center rounded-full border border-[#e1e5eb] bg-white text-[#667085] transition-colors hover:bg-[#f9fafb] disabled:cursor-not-allowed disabled:opacity-60"
          title={uiText("새로고침")}
        >
          <RefreshCw size={20} aria-hidden="true" />
        </button>
      </div>

      {error ? (
        <div className="mx-5 mt-6 rounded-[24px] border border-[#ffd7d7] bg-[#fff5f5] px-5 py-4 text-[15px] font-medium text-[#c24141] md:mx-9">
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="p-8 text-center text-[15px] font-medium text-gray-500">
          {uiText("알림을 불러오는 중")}</div>
      ) : null}

      {!loading && notifications.length === 0 ? (
        <div className="p-8 text-center text-[15px] font-medium text-gray-500">
          {uiText("아직 알림이 없습니다.")}</div>
      ) : null}

      <div className="flex flex-col">
        {notifications.map((notification) => {
          const actorHref = notificationActorHref(notification);
          return (
            <article
              key={notification.id}
              className="flex gap-4 border-b border-[#eaedf2] px-5 py-6 transition-colors hover:bg-[#f9fafb] md:px-9"
            >
              {actorHref ? (
                <Link href={actorHref} className="shrink-0 rounded-full">
                  <ProfileAvatar
                    name={notification.actor_deleted ? uiText("삭제한 캐릭터") : notification.actor_name ?? uiText("알림")}
                    avatarUrl={notification.actor_avatar_url}
                    sizeClassName="size-12"
                    textClassName="text-[20px]"
                  />
                </Link>
              ) : (
                <ProfileAvatar
                  name={notification.actor_deleted ? uiText("삭제한 캐릭터") : notification.actor_name ?? uiText("알림")}
                  avatarUrl={notification.actor_avatar_url}
                  sizeClassName="size-12"
                  textClassName="text-[20px]"
                />
              )}
              <div className="min-w-0 flex-1">
                <div className="mb-2 flex flex-wrap items-center gap-2 text-[14px] font-bold text-[#667085]">
                  <NotificationTypeBadge notification={notification} />
                  <span>{formatDate(notification.created_at)}</span>
                  {notification.read_at ? <span className="text-[#98a2b3]">{uiText("읽음")}</span> : null}
                </div>
                <NotificationMessage notification={notification} actorHref={actorHref} />
              </div>
              {!notification.read_at ? (
                <button
                  type="button"
                  onClick={() => handleRead(notification.id)}
                  disabled={savingId === notification.id}
                  className="inline-flex size-11 shrink-0 items-center justify-center rounded-full border border-[#e1e5eb] bg-white text-[#667085] transition-colors hover:bg-[#f9fafb] disabled:cursor-not-allowed disabled:opacity-60"
                  title={uiText("읽음")}
                >
                  <Check size={20} aria-hidden="true" />
                </button>
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}

function NotificationTypeBadge({ notification }: { notification: NotificationRead }) {
  const uiText = useUiText("social");
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-[#fff0ef] px-3 py-1 text-[#ff6b6b]">
      <NotificationIcon type={notification.notification_type} />
      {uiText(notificationTypeLabel(notification.notification_type))}
    </span>
  );
}

function NotificationMessage({
  notification,
  actorHref,
}: {
  notification: NotificationRead;
  actorHref: string | null;
}) {
  const uiText = useUiText("social");
  const copy = notificationCopy(notification, uiText);
  return (
    <div>
      {copy.href ? (
        <Link
          href={copy.href}
          className="block rounded-[22px] focus:outline-none focus:ring-2 focus:ring-[#ff6b6b]/30"
        >
          <p className="break-words text-[18px] font-extrabold leading-7 text-[#101828]">
            {copy.title}
          </p>
        </Link>
      ) : (
        <p className="break-words text-[18px] font-extrabold leading-7 text-[#101828]">
          {copy.title}
        </p>
      )}
      {copy.actorMeta ? (
        actorHref ? (
          <Link
            href={actorHref}
            className="mt-1 inline-block text-[14px] font-semibold text-[#667085] hover:underline"
          >
            {copy.actorMeta}
          </Link>
        ) : (
          <p className="mt-1 text-[14px] font-semibold text-[#667085]">{copy.actorMeta}</p>
        )
      ) : null}
      {copy.body ? (
        copy.href ? (
          <Link href={copy.href} className="mt-3 block">
            <p className="rounded-[20px] border border-[#eaedf2] bg-[#f9fafb] px-4 py-3 text-[15px] font-medium leading-7 text-[#344054]">
              {copy.body}
            </p>
          </Link>
        ) : (
          <p className="mt-3 rounded-[20px] border border-[#eaedf2] bg-[#f9fafb] px-4 py-3 text-[15px] font-medium leading-7 text-[#344054]">
            {copy.body}
          </p>
        )
      ) : null}
    </div>
  );
}

function notificationCopy(notification: NotificationRead, uiText: (key: string, values?: Record<string, string | number>) => string) {
  const actorName = notification.actor_deleted ? uiText("삭제한 캐릭터") : notification.actor_name ?? uiText("누군가");
  const actorMeta = notification.actor_handle ? `@${notification.actor_handle}` : null;
  const recipientName = notification.recipient_deleted ? uiText("삭제한 캐릭터") : notification.recipient_name ?? uiText("해당 캐릭터");
  const followTargetName = notification.recipient_character_id ? recipientName : uiText("내 프로필");
  const ownedPostText = notification.recipient_character_id
    ? uiText("{{name}}의 게시글", {name: recipientName})
    : uiText("내 게시글");
  const postText = previewText(notification.post_title, notification.post_body);
  const sourceText = previewText(notification.source_post_title, notification.source_post_body);

  switch (notification.notification_type) {
    case "reply":
      return {
        title: uiText("{{actor}} · {{post}}에 답글을 남겼어요.", {actor: actorName, post: ownedPostText}),
        actorMeta,
        body: sourceText ? uiText("답글: {{text}}", {text: sourceText}) : postText ? uiText("원문: {{text}}", {text: postText}) : null,
        href: postHref(notification.source_post_id ?? notification.post_id),
      };
    case "quote":
      return {
        title: uiText("{{actor}} · {{post}}을 인용했어요.", {actor: actorName, post: ownedPostText}),
        actorMeta,
        body: sourceText ? uiText("인용글: {{text}}", {text: sourceText}) : postText ? uiText("원문: {{text}}", {text: postText}) : null,
        href: postHref(notification.source_post_id ?? notification.post_id),
      };
    case "mention":
      return {
        title: uiText("{{actor}} · {{name}}을 멘션했어요.", {actor: actorName, name: recipientName}),
        actorMeta,
        body: postText ? uiText("원문: {{text}}", {text: postText}) : null,
        href: postHref(notification.post_id),
      };
    case "like":
      return {
        title: uiText("{{actor}} · {{post}}을 좋아했어요.", {actor: actorName, post: ownedPostText}),
        actorMeta,
        body: postText ? uiText("원문: {{text}}", {text: postText}) : null,
        href: postHref(notification.post_id),
      };
    case "repost":
      return {
        title: uiText("{{actor}} · {{post}}을 리포스트했어요.", {actor: actorName, post: ownedPostText}),
        actorMeta,
        body: postText ? uiText("원문: {{text}}", {text: postText}) : null,
        href: postHref(notification.post_id),
      };
    case "follow":
      return {
        title: uiText("{{actor}} · {{name}} 팔로우를 시작했어요.", {actor: actorName, name: followTargetName}),
        actorMeta,
        body: null,
        href: notificationActorHref(notification),
      };
    default:
      return {
        title: uiText("{{actor}}의 새 알림이 있어요.", {actor: actorName}),
        actorMeta,
        body: postText,
        href: postHref(notification.post_id),
      };
  }
}

function notificationActorHref(notification: NotificationRead) {
  if (notification.actor_character_id) {
    return `/profiles/characters/${notification.actor_character_id}`;
  }
  if (notification.actor_user_id) {
    return `/profiles/users/${notification.actor_user_id}`;
  }
  return null;
}

function notificationTypeLabel(type: string) {
  switch (type) {
    case "reply":
      return "대꾸";
    case "quote":
      return "인용";
    case "mention":
      return "멘션";
    case "like":
      return "좋아요";
    case "repost":
      return "리포스트";
    case "follow":
      return "팔로우";
    default:
      return "알림";
  }
}

function NotificationIcon({ type }: { type: string }) {
  switch (type) {
    case "reply":
      return <MessageCircle size={15} strokeWidth={2.4} aria-hidden="true" />;
    case "quote":
      return <Quote size={15} strokeWidth={2.4} aria-hidden="true" />;
    case "mention":
      return <AtSign size={15} strokeWidth={2.4} aria-hidden="true" />;
    case "like":
      return <Heart size={15} strokeWidth={2.4} aria-hidden="true" />;
    case "repost":
      return <Repeat2 size={15} strokeWidth={2.4} aria-hidden="true" />;
    case "follow":
      return <UserPlus size={15} strokeWidth={2.4} aria-hidden="true" />;
    default:
      return <Bell size={15} strokeWidth={2.4} aria-hidden="true" />;
  }
}

function previewText(title: string | null, body: string | null) {
  const text = [title, body].filter(Boolean).join(" ").trim();
  if (!text) return null;
  return text.length > 90 ? `${text.slice(0, 90)}...` : text;
}

function postHref(postId: string | null) {
  return postId ? `/posts/${postId}` : null;
}
