import { expect, test } from "@playwright/test";
import { FEED_WORLD, OTHER_FEED_WORLD, feedRoute, ownerId } from "./world-feed-fixture";
import { installNotificationFixture, notificationItem } from "./world-notifications-fixture";

const notices = `/worlds/${FEED_WORLD}/notifications`;
const countPath = `/worlds/${FEED_WORLD}/notifications/unread-count`;

for (const language of ["ko", "en"] as const) test(`one bell, unread markers and one explicit bulk command (${language})`, async ({ page }, info) => {
  const { state } = await installNotificationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
  await page.goto(feedRoute());
  const bell = page.locator(`a[href^="${notices}"]`);
  await expect(bell).toHaveCount(1); await expect(bell).toContainText("99+");
  await expect(bell).toHaveAccessibleName(language === "ko" ? "알림, 읽지 않은 알림 101개" : "Notifications, 101 unread notifications");
  await expect(page.locator("[data-device-scroll-owner=true]")).toHaveCount(1);
  await bell.click(); await expect(page.locator("[data-world-notifications]")).toBeVisible();
  await expect(page.locator("[data-world-notification]")).toHaveCount(2);
  await expect(page.locator("[data-notification-unread]")).toHaveCount(2);
  await expect(page.locator("[data-world-notification] button")).toHaveCount(0);
  expect(state.writes).toEqual([]); expect(state.bulkWrites).toEqual([]);
  const check = page.getByRole("button", { name: language === "ko" ? "모두 읽음으로 표시" : "Mark all as read", exact: true });
  await expect(check).toHaveAttribute("title", language === "ko" ? "모두 읽음으로 표시" : "Mark all as read");
  await check.click();
  await expect(page.locator("[data-notification-unread]")).toHaveCount(0);
  expect(state.count).toBe(0); expect(state.bulkWrites).toEqual([{ world_id: FEED_WORLD, recipient_world_character_id: ownerId(FEED_WORLD) }]);
  await expect(check).toBeDisabled();
  await page.reload(); await expect(page.locator("[data-world-notification]")).toHaveCount(2);
  await expect(page.locator("[data-notification-unread]")).toHaveCount(0); expect(state.bulkWrites).toHaveLength(1);
});

test("home performs one read-only batch, defaults to feed and preserves the World introduction", async ({ page }, info) => {
  const { state, feed } = await installNotificationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto("/");
  const icon = page.getByRole("link", { name: new RegExp(`101`) });
  await expect(icon).toHaveAttribute("href", new RegExp(`${feedRoute()}/?$`));
  await expect(icon.locator("[data-count-badge]")).toHaveText("99+");
  await expect(icon.locator('[data-world-launchability="launchable"]')).toBeVisible();
  expect(state.batchIds).toEqual([[FEED_WORLD, OTHER_FEED_WORLD].sort()]);
  const bounds = await icon.locator("[data-count-badge]").evaluate(el => {
    const r = el.getBoundingClientRect(), parent = el.parentElement!.parentElement!;
    return { width: r.width, overflow: getComputedStyle(parent).overflow, innerClipping: getComputedStyle(parent.querySelector("span")!).overflow };
  });
  expect(bounds.width).toBeGreaterThanOrEqual(26); expect(bounds.overflow).toBe("visible"); expect(bounds.innerClipping).toBe("hidden");
  await icon.click(); await expect(page).toHaveURL(new RegExp(`${feedRoute()}/?$`));
  await expect(page.locator("#world-owner-composer")).toBeVisible();
  await page.getByRole("link", { name: "World", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/worlds/${FEED_WORLD}/?$`));
  await page.goto("/studio");
  const studioOpen = page.locator(`a[href^="${feedRoute()}"]`).first();
  await expect(studioOpen).toBeVisible(); await studioOpen.click();
  await expect(page.locator("#world-owner-composer")).toBeVisible();
  expect(feed.providerCalls).toEqual([]);
});

test("the existing global notifications route reuses the list with its original API", async ({ page }, info) => {
  test.skip(info.project.name === "static-export", "The global route intentionally remains unsupported in static.");
  await installNotificationFixture(page, false, String(info.project.use.baseURL));
  const item = { id: 901, notification_type: "like", post_id: "legacy-original", source_post_id: null,
    actor_user_id: null, actor_character_id: "legacy-actor", recipient_user_id: null, recipient_character_id: "legacy-recipient",
    data: null, actor_deleted: false, recipient_deleted: false, actor_name: "Legacy Actor", actor_handle: "legacy_actor", actor_avatar_url: null,
    recipient_name: "Legacy Recipient", recipient_handle: "legacy_recipient", recipient_avatar_url: null,
    post_title: "Legacy original", post_body: "Legacy original body", source_post_title: null, source_post_body: null, read_at: null as string | null, created_at: "2026-10-15T03:00:00Z" };
  let reads = 0;
  await page.route("**/api/backend/notifications**", route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/backend/notifications") return route.fulfill({ json: { items: [item], next_cursor: null } });
    if (url.pathname === "/api/backend/notifications/901/read") { reads++; item.read_at = "2026-10-15T04:00:00Z"; return route.fulfill({ json: item }); }
    return route.fallback();
  });
  await page.goto("/notifications");
  await expect(page.getByText("Legacy original body", { exact: false })).toBeVisible();
  expect(reads).toBe(0);
  await page.getByRole("button", { name: "읽음으로 표시" }).click();
  await expect(page.getByText("읽음", { exact: true })).toBeVisible(); expect(reads).toBe(1);
});

test("60-second visible polling shares a timer, stops off the feed and resumes immediately", async ({ page }, info) => {
  const { state } = await installNotificationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.clock.install(); await page.goto(feedRoute());
  await expect(page.locator(`a[href^="${notices}"]`)).toContainText("99+");
  const initial = state.reads.filter(path => path === countPath).length;
  await page.clock.runFor(59_000); expect(state.reads.filter(path => path === countPath)).toHaveLength(initial);
  state.count = 1; await page.clock.runFor(1_000);
  await expect(page.locator(`a[href^="${notices}"]`)).toHaveAccessibleName("알림, 읽지 않은 알림 1개");
  expect(state.reads.filter(path => path === countPath)).toHaveLength(initial + 1);
  await page.getByRole("link", { name: "캐릭터", exact: true }).click();
  const stopped = state.reads.length; await page.clock.runFor(120_000); expect(state.reads).toHaveLength(stopped);
});

test("original navigation and leaving notifications never write individual or bulk reads", async ({ page }, info) => {
  const { state } = await installNotificationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(notices); await expect(page.locator("[data-world-notification]")).toHaveCount(2);
  await page.locator('[data-world-notification="2"] a[href*="/posts/"]').first().click();
  await expect(page).toHaveURL(new RegExp(`/worlds/${FEED_WORLD}/posts/notified-reply-2/?$`));
  await expect(page.getByText("Synthetic thread title Synthetic thread body", { exact: true })).toBeVisible();
  expect(state.count).toBe(101); expect(state.writes).toEqual([]); expect(state.bulkWrites).toEqual([]);
  await page.goto(notices); await expect(page.locator('[data-world-notification="2"]')).toBeVisible();
  await expect(page.locator("[data-notification-unread]")).toHaveCount(2);
  await page.getByRole("link", { name: "피드로 돌아가기", exact: true }).click();
  await expect(page.locator(`a[href^="${notices}"]`)).toHaveAccessibleName("알림, 읽지 않은 알림 101개");
  expect(state.writes).toEqual([]); expect(state.bulkWrites).toEqual([]);
});

test("a rejected scope or failed lookup never becomes zero or an empty successful list", async ({ page }, info) => {
  const { state } = await installNotificationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  state.wrongScope = true; await page.goto(feedRoute());
  await expect(page.locator(`a[href^="${notices}"]`)).toHaveAccessibleName("알림 수를 확인하지 못했어요.");
  await expect(page.locator(`a[href^="${notices}"] [data-count-badge]`)).toHaveCount(0);
  state.wrongScope = false; state.listFailures = 1; await page.goto(notices);
  await expect(page.getByText("알림을 불러오지 못했어요. 다시 시도해 주세요.")).toBeVisible();
  await expect(page.getByText("아직 받은 알림이 없어요.")).toHaveCount(0);
  await page.getByRole("button", { name: "다시 시도", exact: true }).click(); await expect(page.locator("[data-world-notification]")).toHaveCount(2);
  state.nextCursor = "page-2"; await page.getByRole("button", { name: "새로고침", exact: true }).click();
  await page.getByRole("button", { name: "더 보기", exact: true }).click(); await expect(page.locator("[data-world-notification]")).toHaveCount(3);
});

test("unconfigured notification profile offers existing management without an implicit ensure", async ({ page }, info) => {
  const { feed, state } = await installNotificationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  feed.missingOwner = true; await page.goto(notices);
  await expect(page.getByRole("link", { name: "World 관리에서 내 프로필을 확인해 주세요." })).toHaveAttribute("href", new RegExp(`/studio/worlds/${FEED_WORLD}/?$`));
  expect(feed.writes.filter(write => write.path.endsWith("/ensure"))).toEqual([]);
  expect(state.reads).toEqual([]); expect(state.writes).toEqual([]);
});

test("home count failure keeps World launchability and later marks retained numbers stale", async ({ page }, info) => {
  const { state } = await installNotificationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  state.batchFailures = 1; await page.clock.install(); await page.goto("/");
  const icon = page.locator(`a[href^="${feedRoute()}"]`);
  await expect(icon).toHaveAccessibleName(/알림 수를 확인하지 못했어요/);
  await expect(icon.locator('[data-world-launchability="launchable"]')).toBeVisible();
  await expect(page.getByText("준비됨", { exact: true })).toBeVisible();
  await page.clock.runFor(60_000); await expect(icon.locator("[data-count-badge]")).toHaveText("99+");
  state.batchFailures = 1; await page.clock.runFor(60_000);
  await expect(icon).toHaveAccessibleName(/이전에 확인한 읽지 않은 알림 101개/);
  await expect(icon.locator('[data-count-badge][data-stale]')).toHaveText("99+");
});

for (const reason of ["revoked", "changed-scope"] as const) test(`a ${reason} response clears previously displayed notification content`, async ({ page }, info) => {
  const { state } = await installNotificationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(notices); await expect(page.locator("[data-world-notification]")).toHaveCount(2);
  if (reason === "revoked") { state.failureStatus = 404; state.listFailures = 1; } else state.wrongScope = true;
  await page.getByRole("button", { name: "새로고침", exact: true }).click();
  await expect(page.getByText("알림을 불러오지 못했어요. 다시 시도해 주세요.")).toBeVisible();
  await expect(page.locator("[data-world-notification]")).toHaveCount(0);
  await expect(page.getByText("아직 받은 알림이 없어요.")).toHaveCount(0);
});

test("revoked home count permission clears the previous badge rather than retaining it as stale", async ({ page }, info) => {
  const { state } = await installNotificationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.clock.install(); await page.goto("/");
  const icon = page.locator(`a[href^="${feedRoute()}"]`); await expect(icon.locator("[data-count-badge]")).toHaveText("99+");
  state.failureStatus = 401; state.batchFailures = 1; await page.clock.runFor(60_000);
  await expect(icon).toHaveAccessibleName(/알림 수를 확인하지 못했어요/);
  await expect(icon.locator("[data-count-badge]")).toHaveCount(0);
  await expect(icon.locator('[data-world-launchability="launchable"]')).toBeVisible();
});

test("an older pending bulk command cannot restore a count after a newer scope rejection", async ({ page }, info) => {
  const { state } = await installNotificationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  let release!: () => void; state.readGate = new Promise<void>(resolve => { release = resolve; });
  await page.goto(notices); await expect(page.locator("[data-world-notification]")).toHaveCount(2);
  await page.getByRole("button", { name: "모두 읽음으로 표시", exact: true }).click();
  await expect.poll(() => state.bulkWrites.length).toBe(1);
  state.wrongScope = true;
  await page.getByRole("button", { name: "새로고침", exact: true }).click();
  await expect(page.locator("[data-world-notification]")).toHaveCount(0);
  await page.getByRole("link", { name: "피드로 돌아가기", exact: true }).click();
  const bell = page.locator(`a[href^="${notices}"]`);
  await expect(bell).toHaveAccessibleName("알림 수를 확인하지 못했어요.");
  release(); state.readGate = null;
  await expect.poll(() => state.completedBulk).toBe(1);
  await expect(bell).toHaveAccessibleName("알림 수를 확인하지 못했어요.");
  await expect(bell.locator("[data-count-badge]")).toHaveCount(0);
});

test("leaving an edited feed uses its existing guard before opening notifications", async ({ page }, info) => {
  const { state } = await installNotificationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(feedRoute()); const input = page.locator("#world-owner-composer textarea");
  await input.fill("Unsaved World draft");
  page.once("dialog", dialog => dialog.dismiss()); await page.locator(`a[href^="${notices}"]`).click();
  await expect(page).toHaveURL(new RegExp(`${feedRoute()}/?$`)); await expect(input).toHaveValue("Unsaved World draft"); expect(state.writes).toEqual([]);
  page.once("dialog", dialog => dialog.accept()); await page.locator(`a[href^="${notices}"]`).click(); await expect(page.locator("[data-world-notifications]")).toBeVisible();
});

for (const count of [0, 1, 99, 100]) test(`home and feed format ${count} without changing the canonical accessible count`, async ({ page }, info) => {
  const { state } = await installNotificationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  state.count = count; state.unavailable.add(OTHER_FEED_WORLD);
  await page.goto("/");
  const icon = page.locator(`a[href^="${feedRoute()}"]`);
  if (count) await expect(icon.locator("[data-count-badge]")).toHaveText(count > 99 ? "99+" : String(count));
  else await expect(icon.locator("[data-count-badge]")).toHaveCount(0);
  await expect(page.locator(`a[href^="${feedRoute(OTHER_FEED_WORLD)}"]`)).toHaveAccessibleName(/알림 수를 확인하지 못했어요/);
  await expect(page.locator('[data-world-launchability="launchable"]')).toHaveCount(2);
  await icon.click();
  await expect(page.locator(`a[href^="${notices}"]`)).toHaveAccessibleName(`알림, 읽지 않은 알림 ${count}개`);
});

test("home uses a single minute batch, pauses hidden, refreshes on return and does not repeat initialization", async ({ page }, info) => {
  const { state, feed } = await installNotificationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.clock.install(); await page.goto("/");
  await expect(page.locator(`a[href^="${feedRoute()}"] [data-count-badge]`)).toHaveText("99+");
  const count = state.batchIds.length, ensures = feed.writes.filter(write => write.path.endsWith("/ensure")).length;
  await page.clock.runFor(59_000); expect(state.batchIds).toHaveLength(count);
  await page.clock.runFor(1000); await expect.poll(() => state.batchIds.length).toBe(count + 1);
  expect(feed.writes.filter(write => write.path.endsWith("/ensure"))).toHaveLength(ensures);
  await page.evaluate(() => { Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" }); document.dispatchEvent(new Event("visibilitychange")); });
  await page.clock.runFor(120_000); expect(state.batchIds).toHaveLength(count + 1);
  state.count = 4;
  await page.evaluate(() => { Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" }); document.dispatchEvent(new Event("visibilitychange")); });
  await expect(page.locator(`a[href^="${feedRoute()}"] [data-count-badge]`)).toHaveText("4");
  expect(state.batchIds).toHaveLength(count + 2);
  expect(feed.writes.filter(write => write.path.endsWith("/ensure")).length).toBeLessThanOrEqual(ensures + 1);
});

test("failed refresh keeps the previous number with an explicit stale label", async ({ page }, info) => {
  const { state } = await installNotificationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.clock.install(); await page.goto(feedRoute());
  const bell = page.locator(`a[href^="${notices}"]`); await expect(bell).toContainText("99+");
  state.countFailures = 1; await page.clock.runFor(60_000);
  await expect(bell).toHaveAccessibleName("알림, 읽지 않은 알림 101개 이전에 확인한 수예요.");
  await expect(bell.locator("[data-count-badge]")).toHaveText("99+");
  await bell.click();
  const writes = state.writes.length;
  await page.locator('[data-world-notification="2"] a[href*="/characters/"]').first().click();
  expect(state.writes).toHaveLength(writes);
});

test("a late count from the previous authenticated principal cannot replace the new scope", async ({ page }, info) => {
  const { state, feed } = await installNotificationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  state.countDelay = 800;
  await page.goto(feedRoute()); await expect.poll(() => state.reads.filter(path => path === countPath).length).toBe(1);
  state.count = 0; state.countDelay = 0; feed.authUserId = "new-local-principal";
  await page.evaluate(() => window.dispatchEvent(new Event("angmoo:auth-changed")));
  const bell = page.locator(`a[href^="${notices}"]`);
  await expect(bell).toHaveAccessibleName("알림, 읽지 않은 알림 0개");
  await expect.poll(() => state.reads.filter(path => path === countPath).length).toBe(2);
  // Let the already admitted older response finish after the new one.
  await expect.poll(() => state.completedCounts.includes(101)).toBe(true);
  await expect(bell).toHaveAccessibleName("알림, 읽지 않은 알림 0개");
  await expect(bell.locator("[data-count-badge]")).toHaveCount(0);
});

for (const language of ["ko", "en"] as const) for (const width of [320, 360, 390, 436, 1280]) test(`layout, badge contrast and keyboard at ${width}px (${language})`, async ({ page }, info) => {
  await page.setViewportSize({ width, height: 850 });
  await installNotificationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
  await page.goto(feedRoute()); const bell = page.locator(`a[href^="${notices}"]`); await expect(bell).toContainText("99+");
  const header = page.locator("[data-feed-header]");
  const geometry = await header.evaluate(el => {
    const center = el.querySelector("[data-feed-header-center]")!.getBoundingClientRect();
    const box = el.getBoundingClientRect(), right = el.querySelector("[data-feed-header-right]")!.getBoundingClientRect();
    return { logoCenter: (center.left + center.right) / 2, headerCenter: (box.left + box.right) / 2, logoRight: center.right, actionsLeft: right.left };
  });
  expect(Math.abs(geometry.logoCenter - geometry.headerCenter)).toBeLessThan(1); expect(geometry.logoRight).toBeLessThanOrEqual(geometry.actionsLeft);
  const rect = await bell.boundingBox(); expect(rect!.width).toBeGreaterThanOrEqual(44); expect(rect!.height).toBeGreaterThanOrEqual(44);
  const contrast = await bell.locator("[data-count-badge]").evaluate(el => {
    const color = getComputedStyle(el);
    const lum = (s: string) => { const rgb = s.match(/[\d.]+/g)!.slice(0,3).map(Number).map(n => n / 255).map(n => n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4); return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722; };
    const a = lum(color.color), b = lum(color.backgroundColor); return (Math.max(a,b) + .05) / (Math.min(a,b) + .05);
  });
  expect(contrast).toBeGreaterThanOrEqual(4.5);
  const backgrounds = await bell.locator("[data-count-badge]").evaluate(el => ({ badge: getComputedStyle(el).backgroundColor,
    selectedFeed: getComputedStyle(document.querySelector('footer a[aria-current="page"],nav a[aria-current="page"]')!).backgroundColor }));
  expect(backgrounds.badge).toBe(backgrounds.selectedFeed);
  await bell.focus(); await expect(bell).toBeFocused(); await page.keyboard.press("Enter"); await expect(page.locator("[data-world-notifications]")).toBeVisible();
  const check = page.getByRole("button", { name: language === "ko" ? "모두 읽음으로 표시" : "Mark all as read", exact: true });
  const refresh = page.getByRole("button", { name: language === "ko" ? "새로고침" : "Refresh", exact: true });
  const checkBox = await check.boundingBox(), refreshBox = await refresh.boundingBox();
  expect(checkBox!.width).toBe(44); expect(checkBox!.height).toBe(44); expect(checkBox!.x + checkBox!.width).toBeLessThan(refreshBox!.x);
  expect(checkBox!.x).toBeGreaterThanOrEqual(0); expect(refreshBox!.x + refreshBox!.width).toBeLessThanOrEqual(width);
  await expect(check.locator("svg")).toHaveAttribute("width", "20");
  await check.focus(); await expect(check).toBeFocused(); await page.keyboard.press("Tab"); await expect(refresh).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: `../artifacts/world-notifications-bulk-20261015/${info.project.name}-${language}-${width}.png` });
});

test("rapid clicks share one command, include older pages and preserve a later arrival", async ({ page }, info) => {
  const { state } = await installNotificationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  let release!: () => void; state.readGate = new Promise<void>(resolve => { release = resolve; }); state.arriveAfterBulk = true;
  state.nextCursor = "page-2";
  await page.goto(notices); await expect(page.locator("[data-world-notification]")).toHaveCount(2);
  await page.getByRole("button", { name: "모두 읽음으로 표시", exact: true }).evaluate(button => {
    for (let index = 0; index < 20; index++) (button as HTMLButtonElement).click();
  });
  await expect.poll(() => state.bulkWrites.length).toBe(1);
  await expect(page.getByRole("button", { name: "모두 읽음으로 표시", exact: true })).toBeDisabled();
  await expect(page.locator('[data-read-all-status="pending"]')).toBeVisible();
  release(); state.readGate = null;
  await expect(page.locator("[data-notification-unread]")).toHaveCount(1);
  await page.getByRole("button", { name: "더 보기", exact: true }).click();
  await expect(page.locator('[data-world-notification="3"] [data-notification-unread]')).toHaveCount(0);
  await page.getByRole("link", { name: "피드로 돌아가기", exact: true }).click();
  await expect(page.locator(`a[href^="${notices}"]`)).toHaveAccessibleName("알림, 읽지 않은 알림 1개");
  expect(state.bulkWrites).toHaveLength(1); expect(state.writes).toEqual([]);
});

test("busy bulk failure keeps unread state and only an explicit second click retries", async ({ page }, info) => {
  const { state } = await installNotificationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  state.readFailures = 1;
  await page.goto(notices); const check = page.getByRole("button", { name: "모두 읽음으로 표시", exact: true });
  await check.click(); await expect(page.locator('[data-read-all-status="failed"]')).toBeVisible();
  await expect(page.locator("[data-notification-unread]")).toHaveCount(2); expect(state.count).toBe(101);
  await page.getByRole("button", { name: "새로고침", exact: true }).click(); expect(state.bulkWrites).toHaveLength(1);
  await check.click(); await expect(page.locator("[data-notification-unread]")).toHaveCount(0);
  expect(state.bulkWrites).toHaveLength(2); expect(state.writes).toEqual([]);
});

test("a lost committed response reconciles by GET without reading the later arrival", async ({ page }, info) => {
  const { state } = await installNotificationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  state.loseBulkResponse = true; state.arriveAfterBulk = true;
  await page.goto(notices); await page.getByRole("button", { name: "모두 읽음으로 표시", exact: true }).click();
  await expect(page.locator('[data-read-all-status="uncertain"]')).toBeVisible();
  await expect(page.locator("[data-notification-unread]")).toHaveCount(1); expect(state.count).toBe(1);
  await page.getByRole("button", { name: "다시 확인", exact: true }).click();
  await page.reload(); await expect(page.locator('[data-read-all-status="uncertain"]')).toBeVisible();
  await expect(page.locator("[data-notification-unread]")).toHaveCount(1);
  expect(state.bulkWrites).toHaveLength(1); expect(state.writes).toEqual([]);
});

test("leaving during a pending bulk command stays navigable and reconciles on return", async ({ page }, info) => {
  const { state } = await installNotificationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  let release!: () => void; state.readGate = new Promise<void>(resolve => { release = resolve; });
  await page.goto(notices); await page.getByRole("button", { name: "모두 읽음으로 표시", exact: true }).click();
  await expect.poll(() => state.bulkWrites.length).toBe(1);
  await page.getByRole("link", { name: "피드로 돌아가기", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`${feedRoute()}/?$`));
  release(); state.readGate = null;
  await expect(page.locator(`a[href^="${notices}"]`)).toHaveAccessibleName("알림, 읽지 않은 알림 0개");
  await page.locator(`a[href^="${notices}"]`).click(); await expect(page.locator("[data-notification-unread]")).toHaveCount(0);
  expect(state.bulkWrites).toHaveLength(1);
});

test("a bounded client timeout stays uncertain and reconciles a late commit without replay", async ({ page }, info) => {
  const { state } = await installNotificationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  let release!: () => void; state.readGate = new Promise<void>(resolve => { release = resolve; });
  await page.clock.install(); await page.goto(notices);
  await page.getByRole("button", { name: "모두 읽음으로 표시", exact: true }).click();
  await expect.poll(() => state.bulkWrites.length).toBe(1);
  await page.clock.runFor(15_000);
  await expect(page.locator('[data-read-all-status="uncertain"]')).toBeVisible();
  await expect(page.getByRole("button", { name: "모두 읽음으로 표시", exact: true })).toBeEnabled();
  expect(state.count).toBe(101); expect(state.bulkWrites).toHaveLength(1);
  release(); state.readGate = null; await expect.poll(() => state.completedBulk).toBe(1);
  await page.getByRole("button", { name: "다시 확인", exact: true }).click();
  await expect(page.locator("[data-notification-unread]")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "모두 읽음으로 표시", exact: true })).toBeDisabled();
  expect(state.bulkWrites).toHaveLength(1);
});
