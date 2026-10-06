import { expect, test } from "@playwright/test";
import type { Page, Route } from "@playwright/test";
import { FEED_WORLD, ownerId } from "./world-feed-fixture";
import { installWorldCharacterManagementFixture, worldCharacterRoute, WORLD_AGENT } from "./world-character-management-fixture";
import { continuityAgentDetail } from "./continuity-fixture";

const graphRoute = `/characters/character-${WORLD_AGENT}/worlds/${FEED_WORLD}/relationship-graph`;
const tinyPng = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=", "base64");
async function installGraph(page: Page) {
  const state = { avatar: "/api/v1/media/assets/synthetic-good/content" as string | null, delay: 0, reads: [] as string[], completed: 0 };
  const handler = async (route: Route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api\/(backend|v1)/, "");
    if (path.endsWith("/relationship-graph")) {
      state.reads.push(path);
      const payload = { world_id: FEED_WORLD, center_world_character_id: WORLD_AGENT,
        nodes: [{ world_character_id: WORLD_AGENT, character_id: `character-${WORLD_AGENT}`, display_name: "Synthetic Responder", is_center: true, avatar_url: state.avatar },
          { world_character_id: ownerId(), character_id: `character-${ownerId()}`, display_name: "사용자", is_center: false, avatar_url: null },
          { world_character_id: "missing-photo", character_id: "character-missing-photo", display_name: "Missing", is_center: false, avatar_url: "/api/v1/media/assets/missing/content" }],
        edges: [{ relationship_state_id: "directed-edge", actor_world_character_id: WORLD_AGENT, target_world_character_id: ownerId(), familiarity: 2, affinity: 1, trust: 3, tension: 0, interaction_count: 4, relationship_version: 2,
          relationship_label: "Synthetic directional relationship", perception: "Synthetic perception", view_updated_at: null, reviewed_at: null, last_event_id: null, last_event_at: null }], evidence: [],
        meta: { template: "neighborhood", source: "ladybug", graph_status: "healthy", truncated: false, projection_lag_seconds: 0, revalidated_node_count: 3, revalidated_edge_count: 1, fallback_reason: null } };
      if (state.delay) await new Promise(resolve => setTimeout(resolve, state.delay));
      state.completed += 1;
      return route.fulfill({ json: payload });
    }
    if (path.endsWith("/relationship-review")) return route.fulfill({ json: { mode: "disabled", configuration: { status: "disabled" }, excluded_counts: {}, states: [], jobs: [] } });
    if (path.endsWith("/synthetic-good/content")) return route.fulfill({ body: tinyPng, contentType: "image/png" });
    if (path.endsWith("/missing/content")) return route.fulfill({ status: 404, body: "" });
    return route.fallback();
  };
  await page.route("**/api/backend/**", handler); await page.route("http://127.0.0.1:8080/api/v1/**", handler);
  return state;
}

for (const language of ["ko", "en"] as const) test(`T77/T78/T88/T89/T90: profile actions and compact real statistics (${language})`, async ({ page }, info) => {
  await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
  await page.goto(worldCharacterRoute());
  const profile = page.locator('[data-world-character-surface="profile"]');
  await expect(profile).toBeVisible();
  const actions = profile.locator("[data-profile-action]");
  expect(await actions.evaluateAll(elements => elements.map(element => element.getAttribute("data-profile-action")))).toEqual(["relationships", "mail", "edit"]);
  const graph = profile.locator('[data-profile-action="relationships"]'), mail = profile.locator('[data-profile-action="mail"]');
  await expect(graph).toHaveAttribute("href", graphRoute + (info.project.name === "static-export" ? "/" : ""));
  await expect(graph).toHaveAccessibleName(language === "ko" ? "Synthetic Responder의 관계망 보기" : "View Synthetic Responder relationships");
  const geometry = await graph.evaluate((element) => {
    const next = element.nextElementSibling!, a = element.getBoundingClientRect(), b = next.getBoundingClientRect();
    return { width: a.width, height: a.height, right: a.right, nextLeft: b.left, color: getComputedStyle(element).color, nextColor: getComputedStyle(next).color,
      icon: element.querySelector("svg")?.getBoundingClientRect().width };
  });
  expect(geometry.width).toBeGreaterThanOrEqual(44); expect(geometry.height).toBeGreaterThanOrEqual(44); expect(geometry.icon).toBe(20);
  expect(geometry.right).toBeLessThanOrEqual(geometry.nextLeft); expect(geometry.color).toBe(geometry.nextColor);
  const metrics = profile.locator("[data-world-social-profile-metrics]");
  await expect(metrics).toBeVisible(); await expect(metrics.locator("dt")).toHaveCount(4);
  expect(await metrics.evaluate(element => ({ top: getComputedStyle(element).borderTopWidth, bottom: getComputedStyle(element).borderBottomWidth }))).toEqual({ top: "0px", bottom: "0px" });
  expect(await metrics.evaluate(element => {
    const body = element.parentElement!;
    return { inProfileBody: Boolean(body.querySelector("h2")), otherStatistics: body.querySelectorAll("dl").length,
      borders: [element, body].flatMap(node => [null, "::before", "::after"].map(pseudo => {
        const style = getComputedStyle(node, pseudo);
        return [style.borderTopWidth, style.borderBottomWidth];
      })) };
  })).toEqual({ inProfileBody: true, otherStatistics: 1, borders: Array.from({ length: 6 }, () => ["0px", "0px"]) });
  await expect(profile.getByText(/팔로잉|캐릭터 팔로워|사람 팔로워|Following|Character followers|Human followers/)).toHaveCount(0);
});

test("T82/T84/T86: graph avatars preserve center, directed arrows and fallback initials", async ({ page }, info) => {
  await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  const state = await installGraph(page);
  await page.goto(graphRoute);
  const graph = page.locator('[data-product-content="relationship-graph"]');
  const nodes = graph.locator("[data-relationship-node]"); await expect(nodes).toHaveCount(3);
  const center = nodes.filter({ has: page.locator('title', { hasText: "Synthetic Responder" }) });
  await expect(center).toHaveAttribute("data-relationship-center", "true");
  await expect(center.locator("img")).toBeVisible(); await expect(center.locator("img")).toHaveAttribute("src", /^blob:/);
  await expect(graph.locator(`[data-relationship-node="${ownerId()}"]`)).toContainText("사");
  await expect(graph.locator('[data-relationship-node="missing-photo"]')).toContainText("M");
  await expect(graph.locator('[data-relationship-node="missing-photo"] img')).toHaveCount(0);
  const arrows = graph.locator('path[marker-end]'); await expect(arrows).toHaveCount(1);
  await expect(graph).toContainText("Synthetic Responder → 사용자");
  expect(state.reads).toHaveLength(1);
  await page.setViewportSize({ width: 960, height: 1660 });
  await page.screenshot({ path: `../artifacts/world-character-management-20261005/screenshots/${info.project.name}-ko-network-avatars.png`, fullPage: true });
});

test("T85/T87: unsafe photo falls back and a repaired photo URL retries", async ({ page }, info) => {
  await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  const state = await installGraph(page); state.avatar = "https://outside.invalid/private.png";
  await page.goto(graphRoute);
  const center = page.locator('[data-relationship-node="synthetic-responder"]');
  await expect(center).toContainText("S"); await expect(center.locator("img")).toHaveCount(0);
  state.avatar = "/api/v1/media/assets/synthetic-good/content";
  await page.getByRole("button", { name: "2단계까지 보기", exact: true }).click();
  await expect(center.locator("img")).toBeVisible();
  await page.setViewportSize({ width: 360, height: 900 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  // A late photo result admitted before a runtime change cannot replace the
  // newly admitted photo, center or identity after that change.
  const beforeReads = state.reads.length, beforeCompleted = state.completed;
  state.delay = 300; state.avatar = "/api/v1/media/assets/missing/content";
  await page.getByRole("button", { name: "직접 관계만 보기", exact: true }).click();
  await expect.poll(() => state.reads.length).toBeGreaterThan(beforeReads);
  state.delay = 0; state.avatar = "/api/v1/media/assets/synthetic-good/content";
  await page.evaluate(() => window.dispatchEvent(new Event("angmoo:desktop-runtime-config-changed")));
  await expect(center.locator("img")).toBeVisible();
  await expect.poll(() => state.completed).toBeGreaterThanOrEqual(beforeCompleted + 2);
  await expect(center.locator("img")).toBeVisible();
  await expect(center).toHaveAttribute("data-relationship-center", "true");
});

test("T77/T78/T89: Device Home profile uses exact scoped graph capability and compact four statistics", async ({ page }, info) => {
  await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  const agent = continuityAgentDetail("global-character");
  const handler = async (route: Route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api\/(backend|v1)/, "");
    if (path === "/agents/global-character") return route.fulfill({ json: { ...agent, activity_profile_readiness: { ...agent.activity_profile_readiness, ready: false, can_view_graph: true, world_id: FEED_WORLD, world_character_id: WORLD_AGENT } } });
    if (path === "/profiles/characters/global-character") return route.fulfill({ json: { post_count: 71, reply_count: 73, liked_post_count: 79, received_like_count: 83, following_count: 101, character_follower_count: 103, human_follower_count: 107 } });
    if (path === "/profiles/characters/global-character/feed") return route.fulfill({ json: { items: [], next_cursor: null } });
    if (path === "/agents/global-character/profile-media/usage") return route.fulfill({ json: {} });
    return route.fallback();
  };
  await page.route("**/api/backend/**", handler); await page.route("http://127.0.0.1:8080/api/v1/**", handler);
  await page.goto("/agents/global-character");
  const action = page.locator('[data-profile-action="relationships"]');
  await expect(action).toHaveAttribute("href", `/characters/global-character/worlds/${FEED_WORLD}/relationship-graph${info.project.name === "static-export" ? "/" : ""}`);
  if (info.project.name !== "static-export") {
    const mail = page.locator('[data-profile-action="mail"]'); await expect(mail).toBeVisible();
    expect(await action.evaluate(element => getComputedStyle(element).color)).toEqual(await mail.evaluate(element => getComputedStyle(element).color));
    const geometry = await action.evaluate(element => ({ right: element.getBoundingClientRect().right, nextLeft: element.nextElementSibling!.getBoundingClientRect().left }));
    expect(geometry.right).toBeLessThanOrEqual(geometry.nextLeft);
  }
  const statistics = page.locator("[data-character-profile-metrics]"); await expect(statistics).toBeVisible();
  expect(await statistics.locator("dd").allTextContents()).toEqual(["71", "73", "79", "83"]);
  await expect(page.locator('a[href*="/follows"]')).toHaveCount(0);
});
