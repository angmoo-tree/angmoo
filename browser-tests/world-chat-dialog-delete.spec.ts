import { expect, test, type Locator } from "@playwright/test";
import { readFileSync } from "node:fs";
import { FEED_WORLD } from "./world-feed-fixture";
import { chatRoute, SYNTHETIC_THREAD } from "./world-social-chat-fixture";
import { installChatDeleteFixture } from "./world-chat-delete-fixture";

const deletionDialog = (page: import("@playwright/test").Page) => page.locator("[data-world-chat-delete-dialog]");
const trash = (row: Locator) => row.locator('button[data-ui-primitive="icon-button"]');
const labels = (language: "ko" | "en") => ({ cancel: language === "ko" ? "취소" : "Cancel", confirm: language === "ko" ? "삭제" : "Delete", retry: language === "ko" ? "같은 대화 다시 삭제" : "Retry deleting this conversation", settings: language === "ko" ? "기억과 진단 보기" : "Open memory and diagnostics" });

for (const language of ["ko", "en"] as const) {
  test(`T33-T35 native memory dialog centers, scrolls and restores focus (${language})`, async ({ page }, info) => {
    const state = await installChatDeleteFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    await page.goto(chatRoute());
    const settings = page.getByRole("button", { name: labels(language).settings, exact: true });
    const field = page.locator("[data-world-chat-surface=thread] textarea");
    await field.fill("Unsent synthetic draft");
    for (const viewport of [{ width: 480, height: 850 }, { width: 960, height: 900 }, { width: 1440, height: 900 }, { width: 1920, height: 1080 }]) {
      await page.setViewportSize(viewport);
      await settings.click();
      const dialog = page.locator("dialog[open]");
      await expect(dialog).toBeVisible();
      const box = (await dialog.boundingBox())!;
      expect(Math.abs(box.x + box.width / 2 - viewport.width / 2)).toBeLessThanOrEqual(2);
      expect(Math.abs(box.y + box.height / 2 - viewport.height / 2)).toBeLessThanOrEqual(2);
      if (viewport.width === (language === "ko" ? 480 : 960)) {
        await page.screenshot({ path: info.outputPath(`memory-dialog-${language}-${viewport.width}.png`) });
      }
      await page.keyboard.press("Escape");
      await expect(settings).toBeFocused();
      await expect(field).toHaveValue("Unsent synthetic draft");
    }
    await settings.click();
    await page.locator("dialog[open]").getByRole("button", { name: language === "ko" ? "대화상자 닫기" : "Close dialog", exact: true }).click();
    await expect(settings).toBeFocused();
    await settings.click(); await page.mouse.click(2, 2);
    await expect(page.locator("dialog[open]")).toHaveCount(0); await expect(settings).toBeFocused();
    state.longDiagnostics = true;
    await page.setViewportSize({ width: 360, height: 480 });
    await settings.click();
    const dialog = page.locator("dialog[open]");
    await dialog.locator("summary").filter({ hasText: language === "ko" ? "검색 진단" : "Search diagnostics" }).click();
    await expect(dialog.locator("ol li")).toHaveCount(40);
    const closeButton = dialog.getByRole("button", { name: language === "ko" ? "대화상자 닫기" : "Close dialog", exact: true });
    const lastButton = dialog.locator("button:not([disabled])").last();
    await lastButton.focus(); await page.keyboard.press("Tab"); await expect(closeButton).toBeFocused();
    await page.keyboard.press("Shift+Tab"); await expect(lastButton).toBeFocused();
    const overflow = await dialog.evaluate(element => ({ vertical: element.scrollHeight > element.clientHeight, horizontal: element.scrollWidth > element.clientWidth }));
    expect(overflow.vertical).toBe(true); expect(overflow.horizontal).toBe(false);
    await dialog.evaluate(element => { element.scrollTop = element.scrollHeight; });
    await dialog.locator("ol li").last().scrollIntoViewIfNeeded();
    await expect(dialog.locator("ol li").last()).toBeInViewport();
    await page.keyboard.press("Escape"); await expect(settings).toBeFocused();
    await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
    await settings.click();
    const zoomBox = (await page.locator("dialog[open]").boundingBox())!;
    expect(zoomBox.x).toBeGreaterThanOrEqual(0); expect(zoomBox.x + zoomBox.width).toBeLessThanOrEqual(361);
    await page.keyboard.press("Escape");
    await page.evaluate(() => { document.documentElement.style.zoom = "1"; });
    const evidenceButton = page.getByRole("button", { name: language === "ko" ? "근거 2개 보기" : "View 2 evidence items", exact: true });
    await evidenceButton.click();
    const inspector = page.locator("[data-world-chat-evidence-dialog]");
    await expect(inspector.getByRole("heading", { name: language === "ko" ? "이 답변의 근거" : "Evidence for this response", exact: true })).toBeVisible();
    await expect(inspector.getByText("Synthetic source 2", { exact: true })).toBeVisible();
    const inspectorClose = inspector.getByRole("button", { name: language === "ko" ? "대화상자 닫기" : "Close dialog", exact: true });
    const lastSource = inspector.locator("a").last();
    await lastSource.focus(); await page.keyboard.press("Tab"); await expect(inspectorClose).toBeFocused();
    await page.keyboard.press("Shift+Tab"); await expect(lastSource).toBeFocused();
    await page.keyboard.press("Escape"); await expect(evidenceButton).toBeFocused();
    await evidenceButton.click(); await page.mouse.click(2, 2);
    await expect(inspector).not.toBeVisible(); await expect(evidenceButton).toBeFocused();
    await expect(field).toHaveValue("Unsent synthetic draft");
    expect(state.deleteRequests).toEqual([]); expect(state.base.base.providerCalls).toEqual([]);
  });

  test(`T36-T39 list delete is scoped, accessible and preserves other row DOM (${language})`, async ({ page }, info) => {
    const state = await installChatDeleteFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    state.count = 2;
    await page.goto(`/worlds/${FEED_WORLD}/chat`);
    const rows = page.locator("[data-thread-row-id]"); await expect(rows).toHaveCount(2);
    const first = rows.first(), second = rows.nth(1);
    await second.evaluate(element => { element.setAttribute("data-preserved-dom", "yes"); });
    expect(await first.locator("a button").count()).toBe(0);
    const button = trash(first); const box = (await button.boundingBox())!;
    expect(box.width).toBeGreaterThanOrEqual(44); expect(box.height).toBeGreaterThanOrEqual(44);
    await expect(button).toHaveAccessibleName(language === "ko" ? "Synthetic Responder와의 대화 삭제" : "Delete conversation with Synthetic Responder");
    await expect(button).toHaveAttribute("title", /Synthetic Responder/);
    await button.click(); await expect(deletionDialog(page).getByRole("button", { name: labels(language).cancel, exact: true })).toBeFocused();
    const close = deletionDialog(page).getByRole("button", { name: language === "ko" ? "대화상자 닫기" : "Close dialog", exact: true });
    const confirm = deletionDialog(page).getByRole("button", { name: labels(language).confirm, exact: true });
    await confirm.focus(); await page.keyboard.press("Tab"); await expect(close).toBeFocused();
    await page.keyboard.press("Shift+Tab"); await expect(confirm).toBeFocused();
    await page.keyboard.press("Escape"); expect(state.deleteRequests).toEqual([]); await expect(button).toBeFocused();
    await button.click(); await deletionDialog(page).getByRole("button", { name: labels(language).cancel, exact: true }).click();
    expect(state.deleteRequests).toEqual([]);
    await button.click(); await page.mouse.click(2, 2); await expect(deletionDialog(page)).not.toBeVisible();
    await expect(button).toBeFocused();
    await button.click(); await close.click(); await expect(button).toBeFocused();
    expect(state.deleteRequests).toEqual([]);
    const readsBeforeDelete = state.reads.filter(path => path.endsWith("/chat/threads")).length;
    state.delay = 350; await button.click();
    await deletionDialog(page).getByRole("button", { name: labels(language).confirm, exact: true }).dblclick();
    await expect(rows).toHaveCount(1); expect(state.deleteRequests).toEqual([SYNTHETIC_THREAD]);
    await expect(rows.first()).toHaveAttribute("data-preserved-dom", "yes");
    await expect(rows.first().locator("a").first()).toBeFocused();
    expect(state.reads.filter(path => path.endsWith("/chat/threads"))).toHaveLength(readsBeforeDelete);
    await trash(rows.first()).click(); await deletionDialog(page).getByRole("button", { name: labels(language).confirm, exact: true }).click();
    await expect(rows).toHaveCount(0);
    await expect(page.getByRole("heading", { name: language === "ko" ? "대화" : "Chat", exact: true })).toBeFocused();
    await expect(page.getByText(language === "ko" ? "아직 시작한 대화가 없어요" : "No chats have started.", { exact: true })).toBeVisible();
    expect(state.base.base.providerCalls).toEqual([]);
  });

  test(`T38-T39/T46 room Settings then Trash preserves draft on cancel and replaces on success (${language})`, async ({ page }, info) => {
    const state = await installChatDeleteFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    await page.setViewportSize({ width: 360, height: 850 });
    await page.goto(chatRoute());
    const header = page.locator("[data-world-chat-surface=thread] > header"), buttons = header.locator("button");
    await expect(buttons).toHaveCount(2); await expect(buttons.first()).toHaveAccessibleName(labels(language).settings);
    const a = (await buttons.first().boundingBox())!, b = (await buttons.last().boundingBox())!;
    expect(a.x + a.width).toBeLessThanOrEqual(b.x); expect(b.x + b.width).toBeLessThanOrEqual(360);
    const navigation = header.locator("a");
    await navigation.first().focus(); await page.keyboard.press("Tab"); await expect(navigation.last()).toBeFocused();
    await page.keyboard.press("Tab"); await expect(buttons.first()).toBeFocused();
    await page.keyboard.press("Tab"); await expect(buttons.last()).toBeFocused();
    const field = page.locator("[data-world-chat-surface=thread] textarea"); await field.fill("Room draft survives cancel");
    const form = page.locator("[data-world-chat-surface=thread] form");
    const chooser = page.waitForEvent("filechooser");
    await form.getByRole("button", { name: language === "ko" ? "사진 첨부" : "Attach photo", exact: true }).click();
    await (await chooser).setFiles({ name: "synthetic-delete-draft.webp", mimeType: "image/webp",
      buffer: readFileSync("../backend/tests/image_integration/fixtures/pixels.webp") });
    await expect(form.locator("img")).toBeVisible();
    const removePhoto = form.getByRole("button", { name: language === "ko" ? "사진 제거" : "Remove image", exact: true });
    await expect(removePhoto).toBeVisible();
    const removeBox = (await removePhoto.boundingBox())!;
    expect(removeBox.height).toBeGreaterThanOrEqual(44);
    expect(await removePhoto.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    expect(await removePhoto.locator("span").first().evaluate(element =>
      element.getBoundingClientRect().height <= parseFloat(getComputedStyle(element).fontSize) * 1.5)).toBe(true);
    await buttons.last().click(); await expect(deletionDialog(page)).toContainText(language === "ko" ? "보내지 않은 글" : "Unsent text");
    await deletionDialog(page).getByRole("button", { name: labels(language).cancel, exact: true }).click(); await expect(field).toHaveValue("Room draft survives cancel");
    await expect(form.locator("img")).toBeVisible(); expect(state.deleteRequests).toEqual([]);
    const screenshotWidth = language === "ko" ? 480 : 960;
    await page.setViewportSize({ width: screenshotWidth, height: 900 });
    await page.screenshot({ path: info.outputPath(`chat-room-settings-trash-${language}-${screenshotWidth}.png`) });
    await page.setViewportSize({ width: 360, height: 850 });
    let leaveQuestions = 0; page.on("dialog", dialog => { leaveQuestions += 1; void dialog.dismiss(); });
    state.delay = 3000;
    await buttons.last().click(); await deletionDialog(page).getByRole("button", { name: labels(language).confirm, exact: true }).click();
    await expect.poll(() => state.deleteRequests.length).toBe(1);
    const opposite = language === "ko" ? "en" : "ko";
    state.base.base.language = opposite;
    await page.evaluate(() => window.dispatchEvent(new Event("angmoo:auth-changed")));
    await expect(deletionDialog(page).getByRole("heading", { name: opposite === "ko" ? "대화 삭제" : "Delete conversation", exact: true })).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`/worlds/${FEED_WORLD}/chat/?$`), { timeout: 10000 }); expect(leaveQuestions).toBe(0);
    await page.goto(chatRoute()); await expect(page.locator("[data-world-chat-surface=thread]")).toHaveCount(0);
    expect(state.deleteRequests).toEqual([SYNTHETIC_THREAD]);
    expect(state.base.base.providerCalls).toEqual([]);
  });
}

for (const mode of ["409", "500", "403", "404", "offline", "corrupt", "wrong_world", "wrong_thread", "lost"] as const) {
  test(`T45 deletion ${mode} keeps room/draft and retries the same identity`, async ({ page }, info) => {
    const state = await installChatDeleteFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), "en");
    state.deleteMode = mode;
    await page.goto(chatRoute());
    const field = page.locator("[data-world-chat-surface=thread] textarea"); await field.fill("Retained text after failure");
    const form = page.locator("[data-world-chat-surface=thread] form");
    if (mode === "500") {
      const chooser = page.waitForEvent("filechooser");
      await form.getByRole("button", { name: "Attach photo", exact: true }).click();
      await (await chooser).setFiles({ name: "synthetic-retained-failed-delete.webp", mimeType: "image/webp",
        buffer: readFileSync("../backend/tests/image_integration/fixtures/pixels.webp") });
      await expect(form.locator("img")).toBeVisible();
    }
    await page.locator("[data-world-chat-surface=thread] > header button").last().click();
    await deletionDialog(page).getByRole("button", { name: "Delete", exact: true }).click();
    await expect(deletionDialog(page).getByRole("alert")).toBeVisible();
    await expect(field).toHaveValue("Retained text after failure"); await expect(page).toHaveURL(new RegExp(SYNTHETIC_THREAD));
    if (mode === "500") await expect(form.locator("img")).toBeVisible();
    state.deleteMode = "ok";
    await deletionDialog(page).getByRole("button", { name: "Retry deleting this conversation", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/worlds/${FEED_WORLD}/chat/?$`));
    expect(state.deleteRequests).toEqual([SYNTHETIC_THREAD, SYNTHETIC_THREAD]);
  });
}

test("T43 header delete stays disabled during a known nonterminal response", async ({ page }, info) => {
  const state = await installChatDeleteFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), "en");
  state.activeResponse = true;
  await page.goto(chatRoute());
  await expect(page.locator("[data-world-chat-surface=thread] > header button").last()).toBeDisabled();
  expect(state.deleteRequests).toEqual([]);
});

test("T47 old deletion cannot redirect after runtime change", async ({ page }, info) => {
  const state = await installChatDeleteFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), "en");
  state.delay = 700;
  await page.goto(chatRoute());
  await page.locator("[data-world-chat-surface=thread] > header button").last().click();
  await deletionDialog(page).getByRole("button", { name: "Delete", exact: true }).click();
  await expect.poll(() => state.deleteRequests.length).toBe(1);
  await page.evaluate(() => { window.__ANGMOO_RUNTIME_CONFIG__ = { profile: "tauri-static", apiBaseUrl: "http://127.0.0.1:8081", graphProvider: "ladybug", launchToken: "new-synthetic-runtime-token-00000000" }; window.dispatchEvent(new Event("angmoo:desktop-runtime-config-changed")); });
  await expect(deletionDialog(page)).not.toBeVisible();
  await page.waitForTimeout(850);
  await expect(page).toHaveURL(new RegExp(SYNTHETIC_THREAD));
});

test("T42 pending deletion keeps native dialog open and blocks repeat and cancellation", async ({ page }, info) => {
  const state = await installChatDeleteFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), "en");
  state.delay = 1000;
  await page.goto(chatRoute());
  await page.locator("[data-world-chat-surface=thread] > header button").last().click();
  const dialog = deletionDialog(page);
  await dialog.getByRole("button", { name: "Delete", exact: true }).click();
  await expect.poll(() => state.deleteRequests.length).toBe(1);
  await expect(dialog.getByRole("button", { name: "Cancel", exact: true })).toBeDisabled();
  await page.keyboard.press("Escape"); await page.mouse.click(2, 2); await expect(dialog).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`/worlds/${FEED_WORLD}/chat/?$`));
  expect(state.deleteRequests).toEqual([SYNTHETIC_THREAD]);
});

test("T47 late 401 from old identity cannot clear replacement auth", async ({ page }, info) => {
  const state = await installChatDeleteFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), "en");
  state.delay = 700; state.deleteMode = "401";
  await page.goto(chatRoute());
  await page.locator("[data-world-chat-surface=thread] > header button").last().click();
  await deletionDialog(page).getByRole("button", { name: "Delete", exact: true }).click();
  await expect.poll(() => state.deleteRequests.length).toBe(1);
  state.ownerId = "replacement-auth-owner";
  await page.evaluate(() => {
    const user = JSON.parse(sessionStorage.getItem("angmoo.user") || "{}");
    sessionStorage.setItem("angmoo.user", JSON.stringify({ ...user, id: "replacement-auth-owner" }));
    window.dispatchEvent(new Event("angmoo:auth-changed"));
  });
  await expect(deletionDialog(page)).not.toBeVisible();
  await page.waitForTimeout(850);
  expect(await page.evaluate(() => JSON.parse(sessionStorage.getItem("angmoo.user") || "{}").id)).toBe("replacement-auth-owner");
  await expect(page).toHaveURL(new RegExp(SYNTHETIC_THREAD));
});

test("T47 pending delete cannot survive navigation into another World", async ({ page }, info) => {
  const state = await installChatDeleteFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), "en");
  state.delay = 700;
  await page.goto(chatRoute());
  await page.locator("[data-world-chat-surface=thread] > header button").last().click();
  await deletionDialog(page).getByRole("button", { name: "Delete", exact: true }).click();
  await expect.poll(() => state.deleteRequests.length).toBe(1);
  await page.goto("/worlds/another-world/chat");
  await expect(deletionDialog(page)).not.toBeVisible();
  await page.waitForTimeout(850);
  await expect(page).toHaveURL(/\/worlds\/another-world\/chat\/?$/);
});

test("T37 a scrolled list preserves a surviving anchor and loaded rows after one deletion", async ({ page }, info) => {
  const state = await installChatDeleteFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), "en");
  await page.setViewportSize({ width: 960, height: 800 });
  await page.goto(`/worlds/${FEED_WORLD}/chat`);
  const rows = page.locator("[data-thread-row-id]"); await expect(rows).toHaveCount(20);
  const target = rows.nth(10), previous = rows.nth(9);
  await previous.evaluate(element => element.setAttribute("data-retained-anchor", "true"));
  await target.evaluate(element => element.scrollIntoView({ block: "center" }));
  const initialY = (await previous.boundingBox())!.y;
  const scrollY = await page.evaluate(() => window.scrollY);
  const reads = state.reads.filter(path => path.endsWith("/chat/threads")).length;
  await trash(target).click(); await deletionDialog(page).getByRole("button", { name: "Delete", exact: true }).click();
  await expect(rows).toHaveCount(19);
  const anchor = page.locator('[data-retained-anchor="true"]');
  expect(Math.abs((await anchor.boundingBox())!.y - initialY)).toBeLessThanOrEqual(2);
  expect(Math.abs(await page.evaluate(() => window.scrollY) - scrollY)).toBeLessThanOrEqual(2);
  expect(state.reads.filter(path => path.endsWith("/chat/threads"))).toHaveLength(reads);
  expect(state.deleteRequests).toEqual([`${SYNTHETIC_THREAD}-10`]);
});

test("T47 a late collection read cannot restore the previous World after navigation", async ({ page }, info) => {
  const state = await installChatDeleteFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), "en");
  state.listDelay = 800;
  await page.goto(`/worlds/${FEED_WORLD}/chat`, { waitUntil: "domcontentloaded" });
  await expect.poll(() => state.reads.filter(path => path.endsWith("/chat/threads")).length, { timeout: 15000 }).toBeGreaterThan(0);
  await page.goto("/worlds/another-world/chat");
  await page.waitForTimeout(1000);
  await expect(page.locator(`[data-world-chat-surface=list][data-world-id="${FEED_WORLD}"]`)).toHaveCount(0);
  await expect(page).toHaveURL(/\/worlds\/another-world\/chat\/?$/);
  expect(state.deleteRequests).toEqual([]);
});

test("T47 a successful old deletion cannot restore auth or navigate after logout", async ({ page }, info) => {
  const state = await installChatDeleteFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), "en");
  state.delay = 700;
  await page.goto(chatRoute());
  await page.locator("[data-world-chat-surface=thread] > header button").last().click();
  await deletionDialog(page).getByRole("button", { name: "Delete", exact: true }).click();
  await expect.poll(() => state.deleteRequests.length).toBe(1);
  state.ownerId = null;
  await page.evaluate(() => {
    sessionStorage.removeItem("angmoo.user"); sessionStorage.removeItem("angmoo.token");
    window.dispatchEvent(new Event("angmoo:auth-changed"));
  });
  await expect(deletionDialog(page)).not.toBeVisible();
  await page.waitForTimeout(850);
  expect(await page.evaluate(() => sessionStorage.getItem("angmoo.user"))).toBeNull();
  await expect(page).not.toHaveURL(new RegExp(`/worlds/${FEED_WORLD}/chat/?$`));
});
