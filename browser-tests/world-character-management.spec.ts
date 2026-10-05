import { expect, test } from "@playwright/test";
import { FEED_WORLD, OTHER_FEED_WORLD, ownerId } from "./world-feed-fixture";
import { installWorldCharacterManagementFixture, worldCharacterRoute, WORLD_AGENT } from "./world-character-management-fixture";

for (const language of ["ko", "en"] as const) {
  test(`T65/T66/T67/T69/T75: shared management tabs and independent Social query (${language})`, async ({ page }, info) => {
    const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    await page.goto(`${worldCharacterRoute()}?tab=likes&keep=original`);
    const surface = page.locator("[data-world-character-management]");
    await expect(surface.getByRole("tab", { name: language === "ko" ? "프로필" : "Profile", exact: true })).toHaveAttribute("aria-selected", "true");
    await expect(surface.locator('[data-world-character-surface="profile"]')).toBeVisible();
    await page.setViewportSize({ width: 960, height: 1660 });
    const worldNavigation = page.getByRole("navigation", { name: language === "ko" ? "World 앱 기능" : "World app navigation", exact: true });
    await expect(worldNavigation).toBeInViewport();
    await page.screenshot({ path: `../artifacts/world-character-management-20261005/screenshots/${info.project.name}-${language}-world-profile.png`, fullPage: true });
    await surface.getByRole("tab", { name: language === "ko" ? "상태" : "Status", exact: true }).click();
    await expect(page).toHaveURL(/view=status/); expect(new URL(page.url()).searchParams.get("tab")).toBe("likes"); expect(new URL(page.url()).searchParams.get("keep")).toBe("original");
    await expect(surface.getByRole("tabpanel").filter({ visible: true })).toContainText(language === "ko" ? "ON · 활동 시간 대기" : "ON · Waiting for activity hours");
    await expect(surface.getByRole("tabpanel").filter({ visible: true }).locator('[data-profile-action="relationships"]')).toHaveCount(0);
    await expect(worldNavigation).toBeInViewport();
    await page.screenshot({ path: `../artifacts/world-character-management-20261005/screenshots/${info.project.name}-${language}-world-status.png`, fullPage: true });
    await surface.getByRole("tab", { name: language === "ko" ? "프로필" : "Profile", exact: true }).click();
    await expect(surface.getByRole("tab", { name: language === "ko" ? "프로필" : "Profile", exact: true })).toHaveAttribute("aria-selected", "true");
    expect(state.management.reads.filter(path => path.endsWith("/management"))).toHaveLength(1);
    expect(state.management.reads.filter(path => path.endsWith("/settings"))).toHaveLength(0);
    expect(state.management.writes).toEqual([]); expect(state.base.base.providerCalls).toEqual([]);
  });

  test(`T71/T73/T74: scoped settings draft survives views and saves only current World (${language})`, async ({ page }, info) => {
    const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    const other = structuredClone(state.management.worlds.get(OTHER_FEED_WORLD));
    await page.goto(`${worldCharacterRoute()}?view=settings&tab=likes`);
    const form = page.locator("[data-world-character-settings-form]");
    const personality = form.locator('textarea[name="personality"]');
    await expect(personality).toHaveValue(`Original personality ${FEED_WORLD}`);
    await page.setViewportSize({ width: 960, height: 1660 });
    await page.screenshot({ path: `../artifacts/world-character-management-20261005/screenshots/${info.project.name}-${language}-world-settings.png`, fullPage: true });
    await personality.fill("World A independent draft");
    await page.getByRole("tab", { name: language === "ko" ? "상태" : "Status", exact: true }).click();
    await expect(form).toBeHidden();
    await page.getByRole("tab", { name: language === "ko" ? "설정" : "Settings", exact: true }).click();
    await expect(personality).toHaveValue("World A independent draft");
    await form.getByRole("button", { name: language === "ko" ? "설정 저장" : "Save settings", exact: true }).click();
    await expect(form.getByRole("status")).toHaveText(language === "ko" ? "이 World의 설정을 저장했어요." : "Saved settings for this World.");
    expect(state.management.writes).toHaveLength(1);
    expect(state.management.writes[0].path).toContain(`/worlds/${FEED_WORLD}/world-characters/${WORLD_AGENT}/settings`);
    expect((state.management.writes[0].body.settings as Record<string, unknown>).personality).toBe("World A independent draft");
    expect(state.management.worlds.get(OTHER_FEED_WORLD)).toEqual(other);
  });

  test(`T73/T75: World user has profile editing with no AI controls (${language})`, async ({ page }, info) => {
    const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    await page.goto(worldCharacterRoute(ownerId()));
    const surface = page.locator("[data-world-character-management]");
    await expect(surface.locator('header').getByText(language === "ko" ? "사용자" : "User", { exact: true }).first()).toBeVisible();
    await expect(surface.getByRole("button", { name: /자율 활동|Run once now|autonomous activity/i })).toHaveCount(0);
    await surface.locator('[data-profile-action="edit"]').click();
    const editor = page.locator("[data-world-character-profile-editor]");
    await editor.locator('input[name="display_name"]').fill("World user edited");
    await editor.getByRole("button", { name: language === "ko" ? "프로필 저장" : "Save profile", exact: true }).click();
    await expect(editor).not.toBeVisible(); await expect(surface.locator('header h1')).toHaveText("World user edited");
    expect(state.management.writes[0].path).toContain(`/worlds/${FEED_WORLD}/world-characters/${ownerId()}/profile`);
    expect(state.management.reads.filter(path => path.endsWith("/settings"))).toEqual([]);
  });
}

test("T71/T74: conflict preserves draft and explicit revision retry uses current version", async ({ page }, info) => {
  const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(`${worldCharacterRoute()}?view=settings`);
  const form = page.locator("[data-world-character-settings-form]"), field = form.locator('textarea[name="personality"]');
  await field.fill("Preserved conflicting draft"); state.management.worlds.get(FEED_WORLD)![1].revision += 1;
  await form.getByRole("button", { name: "설정 저장", exact: true }).click();
  await expect(page.locator("[data-world-character-management]").getByRole("alert")).toContainText("최신 상태"); await expect(field).toHaveValue("Preserved conflicting draft");
  await page.getByRole("button", { name: "최신 상태 확인", exact: true }).click();
  await form.getByRole("button", { name: "최신 버전을 저장 기준으로 사용", exact: true }).click();
  await form.getByRole("button", { name: "설정 저장", exact: true }).click();
  await expect(form.getByRole("status")).toContainText("저장했어요");
  expect(state.management.writes.map(write => write.body.expected_revision)).toEqual([1, 2]);
});

test("T72/T108: run once sends one scoped request and leaves saved ON unchanged", async ({ page }, info) => {
  const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  state.management.writeDelay = 200;
  await page.goto(worldCharacterRoute()); const surface = page.locator("[data-world-character-management]");
  const run = surface.getByRole("button", { name: "지금 한 번 활동", exact: true });
  await run.evaluate(element => { (element as HTMLButtonElement).click(); (element as HTMLButtonElement).click(); });
  await expect(surface.getByRole("status").filter({ hasText: "접수했어요" })).toBeVisible();
  expect(state.management.writes.filter(write => write.path.endsWith("/run-now"))).toHaveLength(1);
  expect(state.management.worlds.get(FEED_WORLD)![1].autonomous_enabled).toBe(true);
});

test("T70/T73/T74: readonly management never loads private settings or exposes edit controls", async ({ page }, info) => {
  const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  state.management.readonly = true;
  await page.goto(`${worldCharacterRoute()}?view=settings`);
  await expect(page.getByText("이 World 캐릭터의 관리 권한이 없어요.", { exact: true })).toBeVisible();
  await expect(page.locator("[data-world-character-settings-form]")).toHaveCount(0);
  expect(state.management.reads.filter(path => path.endsWith("/settings"))).toHaveLength(0);
  await expect(page.locator('[data-profile-action="edit"]')).toHaveCount(0);
  expect(state.management.writes).toEqual([]);
});

test("T71/T73: model choices come from supported verified settings options", async ({ page }, info) => {
  const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(`${worldCharacterRoute()}?view=settings`);
  const form = page.locator("[data-world-character-settings-form]");
  await expect(form.locator('select[name="generation_model"]')).toBeVisible();
  await expect(form.locator('select[name="image_model"] option[value="gpt-image-1.5"]')).toBeDisabled();
  await form.locator('select[name="generation_model"]').selectOption("gemini-3.5-flash-lite");
  await form.locator('select[name="image_model"]').selectOption("flux-2-flex");
  await form.getByRole("button", { name: "설정 저장", exact: true }).click();
  await expect(form.getByRole("status")).toHaveText("이 World의 설정을 저장했어요.");
  const values = state.management.settings.get(`${FEED_WORLD}:${WORLD_AGENT}`)!;
  expect(values.generation_model).toBe("gemini-3.5-flash-lite");
  expect(values.image_model).toBe("flux-2-flex");
});

test("T66/T75: management tabs, long identity and action geometry at widths and 200 percent", async ({ page }, info) => {
  const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  const item = state.management.worlds.get(FEED_WORLD)![1]; item.profile.display_name = "긴 캐릭터 이름 ".repeat(18); item.profile.handle = "long_handle_".repeat(14);
  await page.goto(worldCharacterRoute()); const surface = page.locator("[data-world-character-management]");
  await expect(surface.locator("h1")).toBeVisible();
  for (const width of [360, 390, 436, 480, 768, 960, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
    const boxes = await surface.locator('nav[role="tablist"] button').evaluateAll(elements => elements.map(element => ({ width: element.getBoundingClientRect().width, height: element.getBoundingClientRect().height })));
    expect(Math.max(...boxes.map(box => box.width)) - Math.min(...boxes.map(box => box.width))).toBeLessThan(1);
    expect(boxes.every(box => box.height >= 44)).toBe(true);
  }
  await page.setViewportSize({ width: 480, height: 900 }); await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  await surface.locator('nav[role="tablist"]').scrollIntoViewIfNeeded();
  const zoomedTabs = await surface.locator('nav[role="tablist"] button').evaluateAll(elements => elements.map(element => ({
    left: element.getBoundingClientRect().left, right: element.getBoundingClientRect().right,
    width: element.getBoundingClientRect().width, height: element.getBoundingClientRect().height,
  })));
  expect(zoomedTabs.every(box => box.left >= -1 && box.right <= 481 && box.height >= 88)).toBe(true);
  expect(Math.max(...zoomedTabs.map(box => box.width)) - Math.min(...zoomedTabs.map(box => box.width))).toBeLessThan(1);
});

test("T74: runtime permission change removes private form and preserved draft from DOM", async ({ page }, info) => {
  const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(`${worldCharacterRoute()}?view=settings`);
  const field = page.locator('[data-world-character-settings-form] textarea[name="personality"]'); await field.fill("PRIVATE DRAFT");
  state.management.readonly = true;
  await page.evaluate(() => window.dispatchEvent(new Event("angmoo:desktop-runtime-config-changed")));
  await expect(page.getByText("이 World 캐릭터의 관리 권한이 없어요.", { exact: true })).toBeVisible();
  await expect(page.locator("[data-world-character-settings-form]")).toHaveCount(0);
  expect(await page.locator("body").textContent()).not.toContain("PRIVATE DRAFT");
});

test("T74/T106: late current World read cannot replace another World profile", async ({ page }, info) => {
  const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  state.management.readDelay = 300;
  await page.goto(worldCharacterRoute());
  await page.goto(worldCharacterRoute(WORLD_AGENT, OTHER_FEED_WORLD));
  const surface = page.locator("[data-world-character-management]");
  await expect(surface).toHaveAttribute("data-world-id", OTHER_FEED_WORLD);
  await expect(surface).toContainText(`Original intro ${OTHER_FEED_WORLD}`);
  await expect(surface).not.toContainText(`Original intro ${FEED_WORLD}`);
  expect(state.management.writes).toEqual([]);
});
