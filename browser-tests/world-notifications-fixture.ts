import type { Page, Route } from "@playwright/test";
import type { WorldNotification } from "../frontend/src/features/social/types/world-notifications";
import { FEED_WORLD, OTHER_FEED_WORLD, ownerId, installWorldFeedFixture } from "./world-feed-fixture";

export function notificationItem(id = 1, world = FEED_WORLD): WorldNotification {
  return { id, notification_type: "reply", actor_world_character_id: `mango-${world}`, actor_name: "Mango", actor_handle: "mango", actor_avatar_url: null,
    actor_deleted: false, read_at: null, created_at: "2026-10-15T03:00:00Z", preview_text: `A reply to your post ${id}`,
    target: { kind: "post", post_id: `notified-reply-${id}`, world_character_id: null, can_open: true } };
}

export async function installNotificationFixture(page: Page, staticShell: boolean, baseURL: string, language: "ko" | "en" = "ko") {
  const feed = await installWorldFeedFixture(page, staticShell, baseURL, language);
  const state = {
    count: 101, otherCount: 3, items: [notificationItem(2), notificationItem(1)], nextCursor: null as string | null,
    listFailures: 0, countFailures: 0, batchFailures: 0, readFailures: 0,
    failureStatus: 503,
    listDelay: 0, countDelay: 0, readDelay: 0, wrongScope: false,
    reads: [] as string[], writes: [] as number[], batchIds: [] as string[][], completedCounts: [] as number[], completedReads: [] as number[],
    readGate: null as Promise<void> | null,
    unavailable: new Set<string>(),
  };
  const handler = async (route: Route) => {
    const url = new URL(route.request().url()), path = url.pathname.replace(/^\/api\/(backend|v1)/, "");
    const send = (body: unknown, status = 200) => route.fulfill({ status, json: body });
    const failure = () => send({ detail: "controlled_notification_failure" }, state.failureStatus);
    if (path === "/notifications/world-unread-counts") {
      const ids = [...new Set(url.searchParams.getAll("world_ids"))]; state.batchIds.push(ids); state.reads.push(path);
      if (state.batchFailures-- > 0) return failure();
      return send({ items: ids.map(world => ({ world_id: world, recipient_world_character_id: state.unavailable.has(world) ? null : ownerId(world),
        status: state.unavailable.has(world) ? "unavailable" : "available", unread_count: state.unavailable.has(world) ? null : world === FEED_WORLD ? state.count : state.otherCount })) });
    }
    const match = path.match(/^\/worlds\/([^/]+)\/notifications(?:\/(unread-count|\d+\/read))?$/);
    if (!match) return route.fallback();
    const world = match[1], scope = { world_id: state.wrongScope ? OTHER_FEED_WORLD : world, recipient_world_character_id: ownerId(world) };
    if (route.request().method() === "PATCH") {
      const id = Number(match[2].split("/")[0]); state.writes.push(id);
      if (state.readGate) await state.readGate;
      if (state.readDelay) await new Promise(resolve => setTimeout(resolve, state.readDelay));
      if (state.readFailures-- > 0) return failure();
      const item = state.items.find(item => item.id === id);
      if (!item) return send({ detail: "notification_not_found" }, 404);
      if (!item.read_at) { item.read_at = "2026-10-15T04:00:00Z"; state.count--; }
      await send({ scope, notification_id: id, read_at: item.read_at, unread_count: state.count }); state.completedReads.push(id); return;
    }
    state.reads.push(path);
    if (match[2] === "unread-count") {
      const count = world === FEED_WORLD ? state.count : state.otherCount;
      if (state.countDelay) await new Promise(resolve => setTimeout(resolve, state.countDelay));
      if (state.countFailures-- > 0) return failure();
      await send({ scope, unread_count: count }); state.completedCounts.push(count); return;
    }
    if (state.listDelay) await new Promise(resolve => setTimeout(resolve, state.listDelay));
    if (state.listFailures-- > 0) return failure();
    const cursor = url.searchParams.get("cursor");
    return send({ scope, unread_count: state.count, items: cursor ? [notificationItem(3)] : state.items,
      next_cursor: cursor ? null : state.nextCursor });
  };
  await page.route("**/api/backend/**", handler);
  await page.route("http://127.0.0.1:8080/api/v1/**", handler);
  return { state, feed };
}
