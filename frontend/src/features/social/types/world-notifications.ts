export type NotificationScope = { world_id: string; recipient_world_character_id: string };
export type WorldNotification = {
  id: number;
  notification_type: "like" | "reply" | "quote" | "mention" | "repost" | "follow";
  actor_world_character_id: string | null;
  actor_name: string | null;
  actor_handle: string | null;
  actor_avatar_url: string | null;
  actor_deleted: boolean;
  read_at: string | null;
  created_at: string;
  preview_text: string | null;
  target: { kind: "post" | "world_character"; post_id: string | null; world_character_id: string | null; can_open: boolean };
};
export type WorldNotificationCount = { scope: NotificationScope; unread_count: number };
export type WorldNotificationPage = WorldNotificationCount & { items: WorldNotification[]; next_cursor: string | null };
export type WorldNotificationReadAllResult = WorldNotificationCount & { marked_count: number; read_at: string | null; through_notification_id: number | null };
export type WorldUnreadCount = { world_id: string; recipient_world_character_id: string | null; status: "available" | "unavailable"; unread_count: number | null };
