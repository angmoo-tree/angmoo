import { expect, test, type Page } from "@playwright/test";
import { FEED_WORLD } from "./world-feed-fixture";
import { installWorldCharacterManagementFixture, syntheticWorldCharacter, worldCharacterRoute, WORLD_AGENT } from "./world-character-management-fixture";

function barrier() {
  let release!: () => void;
  const promise = new Promise<void>(resolve => { release = resolve; });
  return { promise, release };
}

async function flushRender(page: Page) {
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
}

test("T67/T74/T77: invalid view, independent query, back/forward and native keyboard order", async ({ page }, info) => {
  const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(`/worlds/${FEED_WORLD}/characters`);
  await page.goto(`${worldCharacterRoute()}?view=invalid&tab=likes&keep=original`);
  const surface = page.locator("[data-world-character-management]");
  const tabs = surface.locator('nav[role="tablist"]');
  const profileTab = tabs.getByRole("tab", { name: "프로필", exact: true });
  await expect(profileTab).toHaveAttribute("aria-selected", "true");
  const profile = surface.locator('[data-world-character-surface="profile"]');
  const network = profile.locator('[data-profile-action="relationships"]');
  const mail = profile.locator('[data-profile-action="mail"]');
  const edit = profile.locator('[data-profile-action="edit"]');
  await expect(mail).toBeEnabled();
  await network.focus(); await expect(network).toBeFocused();
  await page.keyboard.press("Tab"); await expect(mail).toBeFocused();
  await page.keyboard.press("Tab"); await expect(edit).toBeFocused();
  await profileTab.focus(); await page.keyboard.press("ArrowRight");
  await expect(tabs.getByRole("tab", { name: "상태", exact: true })).toBeFocused();
  await expect(profile).toBeHidden();
  await page.keyboard.press("End");
  await expect(tabs.getByRole("tab", { name: "설정", exact: true })).toBeFocused();
  const field = surface.locator('[data-world-character-settings-form] textarea[name="personality"]');
  await expect(field).toBeVisible(); await field.fill("Same World query draft");
  await tabs.getByRole("tab", { name: "설정", exact: true }).focus(); await page.keyboard.press("Home");
  await expect(profileTab).toBeFocused(); await expect(field).toBeHidden();
  expect(new URL(page.url()).searchParams.get("tab")).toBe("likes");
  expect(new URL(page.url()).searchParams.get("keep")).toBe("original");
  await profileTab.focus(); await page.keyboard.press("ArrowLeft");
  await expect(field).toHaveValue("Same World query draft");
  await surface.getByRole("button", { name: "변경 취소", exact: true }).click();
  await tabs.getByRole("tab", { name: "프로필", exact: true }).click();
  const activity = surface.locator("[data-world-character-social-activity]");
  await activity.getByRole("tab", { name: "게시글", exact: true }).click();
  await expect.poll(() => new URL(page.url()).searchParams.get("tab")).toBeNull();
  await activity.getByRole("tab", { name: "좋아요", exact: true }).click();
  await expect.poll(() => new URL(page.url()).searchParams.get("tab")).toBe("likes");
  const retained = new URL(page.url());
  await page.goBack(); await expect(page).toHaveURL(new RegExp(`/worlds/${FEED_WORLD}/characters/?$`));
  await page.goForward(); await expect(profileTab).toHaveAttribute("aria-selected", "true");
  expect(new URL(page.url()).search).toBe(retained.search);
  expect(state.management.writes).toEqual([]); expect(state.base.base.providerCalls).toEqual([]);
});

test("T59/T61: independent pending rows, CAS retry, scroll anchor and an older GET", async ({ page }, info) => {
  const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  state.management.worlds.get(FEED_WORLD)!.push(...Array.from({ length: 12 }, (_, index) => syntheticWorldCharacter(`zz-extra-${index}`, FEED_WORLD)));
  await page.setViewportSize({ width: 960, height: 1200 });
  await page.goto(`/worlds/${FEED_WORLD}/characters`);
  const directory = page.locator('[data-character-dashboard="world-management"]');
  await expect(directory.locator("[data-world-character-id]")).toHaveCount(15);
  const active = directory.locator(`[data-world-character-id="${WORLD_AGENT}"]`), off = directory.locator('[data-world-character-id="off-agent"]');
  const owner = page.locator('[data-device-scroll-owner="true"]');
  await owner.evaluate(element => { element.scrollTop = 190; });
  const anchor = directory.locator('[data-character-autonomy-state="user"]');
  await anchor.evaluate(element => Object.assign(element, { __retained: true }));
  const beforeY = (await anchor.boundingBox())!.y, beforeScroll = await owner.evaluate(element => element.scrollTop);
  const identityLink = active.locator("a").first();
  await identityLink.evaluate(element => (element as HTMLAnchorElement).focus({ preventScroll: true }));
  const first = barrier(); state.management.writeBarrier = first.promise;
  await active.getByRole("button").evaluate(element => (element as HTMLButtonElement).click());
  await expect(active.getByRole("button")).toBeDisabled(); await expect(off.getByRole("button")).toBeEnabled();
  await off.getByRole("button").evaluate(element => (element as HTMLButtonElement).click());
  await expect(off.getByRole("button")).toBeDisabled();
  first.release(); state.management.writeBarrier = null;
  await expect(active).toHaveAttribute("data-character-autonomy-state", "off");
  await expect(off).toHaveAttribute("data-character-autonomy-state", "on");
  await flushRender(page);
  expect(await anchor.evaluate(element => (element as HTMLElement & { __retained?: boolean }).__retained)).toBe(true);
  expect(Math.abs((await anchor.boundingBox())!.y - beforeY)).toBeLessThanOrEqual(2);
  expect(Math.abs(await owner.evaluate(element => element.scrollTop) - beforeScroll)).toBeLessThanOrEqual(2);
  await expect(identityLink).toBeFocused();
  state.management.failure = 409;
  await active.getByRole("button").evaluate(element => (element as HTMLButtonElement).click());
  await expect(directory.getByRole("alert")).toContainText("최신");
  await expect(active.getByRole("button")).toBeEnabled(); await expect(active).toHaveAttribute("data-character-autonomy-state", "off");
  state.management.failure = 0;
  const read = barrier(); state.management.readBarrier = read.promise;
  const reads = state.management.reads.length;
  const completedGets = state.management.completed.filter(entry => entry.method === "GET").length;
  await directory.getByRole("button", { name: "다시 시도", exact: true }).click();
  await expect.poll(() => state.management.reads.length).toBe(reads + 1);
  state.management.readBarrier = null;
  await active.getByRole("button").evaluate(element => (element as HTMLButtonElement).click());
  await expect(active).toHaveAttribute("data-character-autonomy-state", "on");
  read.release();
  await expect.poll(() => state.management.completed.filter(entry => entry.method === "GET").length).toBe(completedGets + 1);
  await flushRender(page);
  await expect(active).toHaveAttribute("data-character-autonomy-state", "on");
  await expect(directory.locator("[data-character-summary]")).toContainText("ON 2 · OFF 12");
  expect(state.management.writes).toHaveLength(4); expect(state.base.base.providerCalls).toEqual([]);
});

test("T74: a pending profile success cannot close or replace a draft after runtime renewal", async ({ page }, info) => {
  const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  state.management.authOwner = "local-owner";
  await page.goto(worldCharacterRoute());
  const profile = page.locator('[data-world-character-surface="profile"]'), editor = page.locator("[data-world-character-profile-editor]");
  await profile.locator('[data-profile-action="edit"]').click();
  await editor.locator('textarea[name="intro"]').fill("Retired profile request");
  const write = barrier(); state.management.writeBarrier = write.promise;
  await editor.getByRole("button", { name: "프로필 저장", exact: true }).click();
  await expect.poll(() => state.management.writes.length).toBe(1);
  state.management.writeBarrier = null;
  await page.evaluate(() => {
    const current = (window as Window & { __ANGMOO_RUNTIME_CONFIG__?: Record<string, unknown> }).__ANGMOO_RUNTIME_CONFIG__;
    if (current) current.launchToken = "renewed-world-profile-synthetic-token-00000000";
    window.dispatchEvent(new Event("angmoo:desktop-runtime-config-changed"));
  });
  await expect(editor).toBeHidden(); await expect(profile).toBeVisible();
  await profile.locator('[data-profile-action="edit"]').click();
  await editor.locator('textarea[name="intro"]').fill("Current runtime draft");
  write.release();
  await expect.poll(() => state.management.completed.filter(entry => entry.path.endsWith("/profile")).length).toBe(1);
  await flushRender(page);
  await expect(editor).toBeVisible(); await expect(editor.locator('textarea[name="intro"]')).toHaveValue("Current runtime draft");
  expect(await page.evaluate(() => JSON.parse(sessionStorage.getItem("angmoo.user") || "{}").id)).toBe("local-owner");
  expect(state.management.writes).toHaveLength(1); expect(state.base.base.providerCalls).toEqual([]);
});

test("T61/T74: an old settings 401 cannot clear a renewed session with the same owner", async ({ page }, info) => {
  const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  state.management.authOwner = "local-owner";
  await page.goto(`${worldCharacterRoute()}?view=settings`);
  const form = page.locator("[data-world-character-settings-form]"), field = form.locator('textarea[name="personality"]');
  await field.fill("Settings draft from the retired session");
  const write = barrier(); state.management.writeBarrier = write.promise; state.management.failure = 401;
  await form.getByRole("button", { name: "설정 저장", exact: true }).click();
  await expect.poll(() => state.management.writes.length).toBe(1);
  state.management.writeBarrier = null; state.management.failure = 0; state.management.authMeFailures = 1;
  const bootstrap = page.waitForResponse(response => /\/auth\/local\/session$/.test(new URL(response.url()).pathname));
  await page.evaluate(() => window.dispatchEvent(new Event("angmoo:auth-changed")));
  expect((await bootstrap).ok()).toBe(true);
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem("angmoo.user") || "{}").id)).toBe("local-owner");
  write.release();
  await expect.poll(() => state.management.completed.filter(entry => entry.path.endsWith("/settings") && entry.method === "PATCH").length).toBe(1);
  await expect(field).toBeEnabled(); await expect(field).toHaveValue("Settings draft from the retired session");
  await expect(form.getByRole("status")).toHaveCount(0); await expect(page.locator('[data-world-character-management] [role="alert"]')).toHaveCount(0);
  await field.fill("Renewed session draft"); await flushRender(page); await expect(field).toHaveValue("Renewed session draft");
  expect(await page.evaluate(() => JSON.parse(sessionStorage.getItem("angmoo.user") || "{}").id)).toBe("local-owner");
  expect(state.management.worlds.get(FEED_WORLD)![1].autonomous_enabled).toBe(true);
  expect(state.base.base.providerCalls).toEqual([]);
});

test("T61/T74: a pending run result cannot restore private controls or status after logout", async ({ page }, info) => {
  const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  state.management.authOwner = "local-owner";
  await page.goto(worldCharacterRoute());
  const surface = page.locator("[data-world-character-management]");
  const write = barrier(); state.management.writeBarrier = write.promise;
  await surface.getByRole("button", { name: "지금 한 번 활동", exact: true }).click();
  await expect.poll(() => state.management.writes.filter(entry => entry.path.endsWith("/run-now")).length).toBe(1);
  state.management.writeBarrier = null; state.management.authOwner = null;
  await page.evaluate(() => { sessionStorage.removeItem("angmoo.user"); window.dispatchEvent(new Event("angmoo:auth-changed")); });
  await expect(surface).toHaveCount(0);
  write.release();
  await expect.poll(() => state.management.completed.filter(entry => entry.path.endsWith("/run-now")).length).toBe(1);
  await flushRender(page);
  expect(await page.evaluate(() => sessionStorage.getItem("angmoo.user"))).toBeNull();
  await expect(page.locator("[data-world-character-settings-form], [data-world-character-profile-editor]")).toHaveCount(0);
  await expect(page.getByText("이 World의 활동 요청을 접수했어요.", { exact: true })).toHaveCount(0);
  expect(state.management.worlds.get(FEED_WORLD)![1].autonomous_enabled).toBe(true);
  expect(state.management.writes).toHaveLength(1); expect(state.base.base.providerCalls).toEqual([]);
});
