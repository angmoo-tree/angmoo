import { expect, test } from "@playwright/test";
import { FEED_WORLD, OTHER_FEED_WORLD, feedRoute, installWorldFeedFixture } from "./world-feed-fixture";

test.afterEach(async ({ request }, info) => {
  const response = await request.get("http://127.0.0.1:3394/fixture/evidence");
  await info.attach("actual-http-evidence", { body: await response.body(), contentType: "application/json" });
});

test("committed source → real HTTP bulk read → selected reply and reconciled home; two Worlds and principals", async ({ page, request }, info) => {
  const api = "http://127.0.0.1:3394";
  await request.post(`${api}/fixture/principal/owner`);
  await request.post(`${api}/fixture/reset`);
  const before = await (await request.get(`${api}/fixture/evidence`)).json();
  const baseURL = String(info.project.use.baseURL);
  await installWorldFeedFixture(page, info.project.name === "static-export", baseURL);
  // Auth/environment is controlled; every scoped World/Social response below
  // comes from the actual routers and file SQLite without rewriting JSON.
  const forward = async (route: import("@playwright/test").Route) => {
    const original = route.request(), url = new URL(original.url());
    const path = url.pathname.replace(/^\/api\/(backend|v1)/, "");
    if (!path.startsWith("/notifications/") && !/^\/worlds\/(mine(?:\/|$)|[^/]+\/(notifications|owner-character|manual-social))/.test(path)) return route.fallback();
    const response = await route.fetch({ url: `${api}/api/v1${path}${url.search}`, headers: { ...original.headers(), host: new URL(baseURL).host, origin: baseURL }, maxRetries: 0 });
    return route.fulfill({ response });
  };
  await page.route("**/api/backend/**", forward);
  await page.route("http://127.0.0.1:8080/api/v1/**", forward);
  await page.goto("/");
  const icon = page.locator(`a[href="${feedRoute()}"],a[href="${feedRoute()}/"]`);
  await expect(icon.locator("[data-count-badge]")).toHaveText("1");
  await icon.click();
  const notices = `/worlds/${FEED_WORLD}/notifications`;
  await expect(page.locator(`a[href^="${notices}"]`)).toHaveAccessibleName("알림, 읽지 않은 알림 1개");
  await page.locator(`a[href^="${notices}"]`).click();
  await expect(page.locator("[data-world-notification]")).toHaveCount(1);
  await expect(page.locator("[data-notification-unread]")).toHaveCount(1);
  expect((await (await request.get(`${api}/fixture/evidence`)).json()).notifications.find((n: {world: string}) => n.world === FEED_WORLD)?.read).toBe(false);
  await page.getByRole("button", { name: "모두 읽음으로 표시", exact: true }).click();
  await expect(page.locator("[data-notification-unread]")).toHaveCount(0);
  await page.locator("[data-world-notification] a[href*='/posts/']").first().click();
  await expect(page).toHaveURL(new RegExp(`/posts/${before.selected[FEED_WORLD]}/?$`));
  await expect(page.getByText(`A real committed reply in ${FEED_WORLD}`, { exact: false })).toBeVisible();
  await expect.poll(async () => (await (await request.get(`${api}/fixture/evidence`)).json()).notifications.find((n: {world: string}) => n.world === FEED_WORLD)?.read).toBe(true);
  await page.goto("/"); await expect(page.locator(`a[href^="${feedRoute()}"] [data-count-badge]`)).toHaveCount(0);
  await expect(page.locator(`a[href^="${feedRoute(OTHER_FEED_WORLD)}"] [data-count-badge]`)).toHaveText("1");
  const after = await (await request.get(`${api}/fixture/evidence`)).json();
  expect(after.requests.filter((r: {method: string; path: string}) => r.method === "POST" && r.path.endsWith("/notifications/read-all"))).toHaveLength(1);
  expect(after.requests.filter((r: {method: string; path: string}) => r.method === "PATCH" && r.path.endsWith("/read"))).toHaveLength(0);
  expect(after.notifications.every((n: {handled: boolean}) => !n.handled)).toBe(true);
  expect(after.relationship_count).toBe(before.relationship_count); expect(after.foreign_key_violations).toEqual([]); expect(after.outbound).toEqual([]); expect(after.provider_calls).toBe(0);
  await request.post(`${api}/fixture/principal/outsider`);
  const denied = await request.get(`${api}/api/v1/worlds/${FEED_WORLD}/notifications`, { headers: { Origin: baseURL } });
  expect(denied.status()).toBe(404);
  await request.post(`${api}/fixture/principal/owner`);
  await page.screenshot({ path: `../artifacts/world-notifications-bulk-20261015/${info.project.name}-actual-http-home.png` });
});
