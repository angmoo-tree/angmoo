import type { NotificationRead } from "../types/community";

export function notificationCopy(notification: NotificationRead, uiText: (key: string, values?: Record<string, string | number>) => string) {
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

export function notificationActorHref(notification: NotificationRead) {
  if (notification.actor_character_id) {
    return `/profiles/characters/${notification.actor_character_id}`;
  }
  if (notification.actor_user_id) {
    return `/profiles/users/${notification.actor_user_id}`;
  }
  return null;
}

function previewText(title: string | null, body: string | null) {
  const text = [title, body].filter(Boolean).join(" ").trim();
  if (!text) return null;
  return text.length > 90 ? `${text.slice(0, 90)}...` : text;
}

function postHref(postId: string | null) {
  return postId ? `/posts/${postId}` : null;
}
