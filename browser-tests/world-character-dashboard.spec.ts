import { expect, test } from "@playwright/test";
import { FEED_WORLD, OTHER_FEED_WORLD, ownerId } from "./world-feed-fixture";
import { installWorldCharacterManagementFixture, syntheticWorldCharacter, WORLD_AGENT } from "./world-character-management-fixture";
import { sortWorldCharactersForDashboard } from "../frontend/src/features/characters/utils/world-character-dashboard-presentation";
import type { WorldCharacterDashboardItem } from "../frontend/src/features/characters/types/world-character-dashboard";

for (const language of ["ko", "en"] as const) {
  test(`T49/T51/T53/T54/T62: scoped cards, user-first ordering and exact summary (${language})`, async ({ page }, info) => {
    const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    await page.goto(`/worlds/${FEED_WORLD}/characters`);
    const directory = page.locator('[data-character-dashboard="world-management"]');
    await expect(directory).toBeVisible();
    const rows = directory.locator("[data-character-id]");
    await expect(rows).toHaveCount(3);
    expect(await rows.evaluateAll(elements => elements.map(element => element.getAttribute("data-world-character-id")))).toEqual([ownerId(), WORLD_AGENT, "off-agent"]);
    await expect(directory.locator("[data-character-summary]")).toHaveText(language === "ko" ? "전체 3 · 자율활동 ON 1 · OFF 1 · 사용자 1" : "Total 3 · Autonomy ON 1 · OFF 1 · Users 1");
    const user = rows.first();
    await expect(user.getByText(language === "ko" ? "사용자" : "User", { exact: true })).toBeVisible();
    await expect(user.getByRole("button")).toHaveCount(0);
    await expect(user).not.toContainText(language === "ko" ? "외부 연결" : "External");
    await expect(user.locator("a").first()).toHaveAttribute("href", `/worlds/${FEED_WORLD}/characters/${ownerId()}${info.project.name === "static-export" ? "/" : ""}`);
    await expect(directory.locator('a[href*="/agents"]')).toHaveCount(0);
    expect(state.management.writes).toEqual([]); expect(state.base.base.providerCalls).toEqual([]);
    await page.setViewportSize({ width: 960, height: 1660 });
    await page.screenshot({ path: `../artifacts/world-character-management-20261005/screenshots/${info.project.name}-${language}-world-cards.png`, fullPage: true });
  });

  test(`T56/T57/T61: scoped toggle keeps cards and other World state (${language})`, async ({ page }, info) => {
    const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    state.management.writeDelay = 300;
    const other = structuredClone(state.management.worlds.get(OTHER_FEED_WORLD));
    await page.goto(`/worlds/${FEED_WORLD}/characters`);
    const directory = page.locator('[data-character-dashboard="world-management"]');
    const row = directory.locator(`[data-world-character-id="${WORLD_AGENT}"]`);
    await expect(row).toBeVisible();
    await row.evaluate(element => Object.assign(element, { __sentinel: "kept" }));
    const button = row.getByRole("button");
    await button.evaluate(element => { (element as HTMLButtonElement).click(); (element as HTMLButtonElement).click(); });
    await expect(button).toBeDisabled();
    await expect(row).toHaveAttribute("data-character-autonomy-state", "off");
    expect(await row.evaluate(element => (element as HTMLElement & { __sentinel?: string }).__sentinel)).toBe("kept");
    expect(state.management.writes).toHaveLength(1);
    expect(state.management.writes[0].path).toBe(`/worlds/${FEED_WORLD}/world-characters/${WORLD_AGENT}/deactivate`);
    expect(state.management.writes[0].body.expected_revision).toBe(1);
    expect(state.management.worlds.get(OTHER_FEED_WORLD)).toEqual(other);
    await expect(directory.locator("[data-character-summary]")).toContainText(language === "ko" ? "ON 0 · OFF 2" : "ON 0 · OFF 2");
  });
}

test("T55/T63: long content stays inside the shared card layout across viewports", async ({ page }, info) => {
  const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  const character = state.management.worlds.get(FEED_WORLD)![1];
  character.profile.display_name = "긴 캐릭터 이름 ".repeat(15); character.profile.handle = "long_handle_".repeat(10); character.profile.intro = "긴 소개 ".repeat(90);
  await page.goto(`/worlds/${FEED_WORLD}/characters`);
  await expect(page.locator('[data-character-dashboard="world-management"] [data-character-id]')).toHaveCount(3);
  for (const width of [360, 390, 436, 480, 768, 960, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
    const boxes = await page.locator('[data-character-dashboard="world-management"] [data-character-id] button').evaluateAll(buttons => buttons.map(button => ({ width: button.getBoundingClientRect().width, height: button.getBoundingClientRect().height })));
    expect(boxes.every(box => box.width >= 44 && box.height >= 44)).toBe(true);
  }
});

test("T50/T61: scoped malformed and forbidden reads fail closed", async ({ page }, info) => {
  const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  state.management.corrupt = true;
  await page.goto(`/worlds/${FEED_WORLD}/characters`);
  await expect(page.locator('[data-character-dashboard="world-management"] [role="alert"]')).toBeVisible();
  await expect(page.locator('[data-character-dashboard="world-management"] [data-character-id]')).toHaveCount(0);
  expect(state.management.writes).toEqual([]);
});

test("T53: equal activity times, absent values and identity ties keep order through locale changes", async ({ page }, info) => {
  const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  const user = syntheticWorldCharacter(ownerId()); user.profile.display_name = "ZZZ";
  const a = syntheticWorldCharacter("actor-a", FEED_WORLD, true), b = syntheticWorldCharacter("actor-b", FEED_WORLD, true);
  a.profile.display_name = b.profile.display_name = "동일 이름";
  a.recent_activity!.occurred_at = "2026-10-05T01:00:00Z";
  b.recent_activity!.occurred_at = "2026-10-05T10:00:00+09:00";
  const c = syntheticWorldCharacter("actor-c", FEED_WORLD, true), d = syntheticWorldCharacter("actor-d", FEED_WORLD, true);
  c.profile.display_name = d.profile.display_name = "AAA"; c.recent_activity = d.recent_activity = null;
  const off = syntheticWorldCharacter("off-last", FEED_WORLD); off.recent_activity!.occurred_at = "2100-01-01T00:00:00Z";
  const input = [off, b, d, user, c, a], preserved = structuredClone(input);
  const expected = [ownerId(), "actor-a", "actor-b", "actor-c", "actor-d", "off-last"];
  expect(sortWorldCharactersForDashboard(input as WorldCharacterDashboardItem[]).map(item => item.profile.world_character_id)).toEqual(expected);
  expect(input).toEqual(preserved);
  state.management.worlds.set(FEED_WORLD, input);
  await page.goto(`/worlds/${FEED_WORLD}/characters`);
  const rows = page.locator('[data-character-dashboard="world-management"] [data-world-character-id]');
  await expect(rows).toHaveCount(6);
  expect(await rows.evaluateAll(elements => elements.map(element => element.getAttribute("data-world-character-id")))).toEqual(expected);
  state.base.base.language = "en";
  await page.evaluate(() => window.dispatchEvent(new Event("angmoo:auth-changed")));
  await expect(page.locator("[data-character-summary]")).toHaveText("Total 6 · Autonomy ON 4 · OFF 1 · Users 1");
  expect(await rows.evaluateAll(elements => elements.map(element => element.getAttribute("data-world-character-id")))).toEqual(expected);
  expect(state.management.writes).toEqual([]); expect(state.base.base.providerCalls).toEqual([]);
});
