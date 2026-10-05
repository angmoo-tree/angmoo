import { expect, test, type Locator, type Page } from "@playwright/test";
import { installPostReactionFixture } from "./world-post-reactions-fixture";
import { FEED_WORLD, feedRoute, profileRoute } from "./world-feed-fixture";
import { detailRoute, SYNTHETIC_ROOT, SYNTHETIC_REPLY } from "./world-social-chat-fixture";

const surface = (page: Page) => page.locator('[data-world-social-surface="detail"]');
const heart = (row: Locator) => row.locator('button[aria-pressed]');
const events = (page: Page) => page.evaluate(() => (window as unknown as { __reactionEvents: unknown[] }).__reactionEvents);
async function sentinel(locator: Locator) { await locator.evaluate(element => Object.assign(element, { __retained: true })); }
async function retained(locator: Locator) { return locator.evaluate(element => Boolean((element as HTMLElement & { __retained?: boolean }).__retained)); }

for (const language of ["ko", "en"] as const) {
  for (const selected of [SYNTHETIC_ROOT, SYNTHETIC_REPLY, "synthetic-leaf"]) test(`T01–T06/T09: title and replies precede the same composer (${selected}, ${language})`, async ({ page }, info) => {
    await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    await page.goto(detailRoute(selected));
    await expect(surface(page).getByRole("heading", { name: language === "ko" ? "게시글" : "post", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: /게시글과 답글|Posts and replies/ })).toHaveCount(0);
    const form = surface(page).locator("form"), heading = surface(page).locator("h3");
    await expect(form).toHaveCount(1); await expect(form.locator("textarea")).toHaveAttribute("maxlength", "1000");
    await expect(form.locator("textarea")).toHaveAccessibleName(language === "ko" ? "답글" : "Reply");
    const order = await form.evaluate(element => {
      const heading = element.parentElement!.querySelector("h3")!, section = heading.parentElement!;
      return { follows: Boolean(heading.compareDocumentPosition(element) & Node.DOCUMENT_POSITION_FOLLOWING), top: element.getBoundingClientRect().top,
        end: section.getBoundingClientRect().bottom, placeholder: element.querySelector("textarea")!.getAttribute("placeholder") };
    });
    expect(order.follows).toBe(true); expect(order.top).toBeGreaterThanOrEqual(order.end - 1); expect(order.placeholder).toBeNull();
    if (selected === "synthetic-leaf") { await expect(heading).toHaveText(language === "ko" ? "답글 0" : "0 replies"); await expect(surface(page).getByText(language === "ko" ? "아직 공개된 답글이 없어요." : "No public replies yet.", { exact: true })).toBeVisible(); }
    else await expect(surface(page).locator('[data-social-post-row="synthetic-leaf"]')).toBeVisible();
    await expect(form.locator('button[type="submit"]')).toHaveText("");
  });

  test(`T04/T11–T13: left header geometry stays fixed across widths and locale (${language})`, async ({ page }, info) => {
    const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    state.base.base.displayName = "LongSyntheticWorldOwnerName".repeat(4);
    for (const post of state.base.posts.slice(0, 3)) {
      post.author_name = "LongSyntheticCharacterName".repeat(4);
      post.body = "Original long paragraph. ".repeat(80);
    }
    await page.goto(detailRoute()); const form = surface(page).locator("form"); await form.locator("textarea").fill("Original unsent draft");
    for (const width of [360, 390, 436, 480, 768, 960, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      const boxes = await surface(page).locator("header").first().evaluate(element => {
        const back = element.querySelector("a")!.getBoundingClientRect(), title = element.querySelector("h2")!.getBoundingClientRect(), refresh = element.querySelector("button")!.getBoundingClientRect();
        return { gap: title.left - back.right, back: back.toJSON(), title: title.toJSON(), refresh: refresh.toJSON(), overflow: document.documentElement.scrollWidth - innerWidth };
      });
      expect(boxes.gap).toBeCloseTo(12, 0); expect(boxes.back.width).toBeGreaterThanOrEqual(44); expect(boxes.back.height).toBeGreaterThanOrEqual(44);
      expect(boxes.refresh.left).toBeGreaterThan(boxes.title.right); expect(boxes.overflow).toBeLessThanOrEqual(1);
      if (width === 390 || width === 960) await page.screenshot({ path: info.outputPath(`detail-${language}-${width}.png`) });
    }
    state.base.base.language = language === "ko" ? "en" : "ko";
    await page.evaluate(() => window.dispatchEvent(new Event("angmoo:auth-changed")));
    await expect(form.locator("textarea")).toHaveValue("Original unsent draft");
    await expect(surface(page).getByRole("heading", { name: language === "ko" ? "post" : "게시글", exact: true })).toBeVisible();
  });

  test(`T09/T12/T13: keyboard order and two hundred percent detail layout (${language})`, async ({ page }, info) => {
    const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    await page.goto(detailRoute("synthetic-leaf"));
    const detail = surface(page), field = detail.locator("form textarea"), send = detail.locator('form button[type="submit"]');
    await expect(field).toBeVisible(); await field.fill(" "); await expect(send).toBeDisabled();
    await field.fill("Preserved keyboard draft");
    const back = detail.locator("header a").first(), refresh = detail.locator("header button").first();
    await back.focus(); await page.keyboard.press("Tab"); await expect(refresh).toBeFocused();
    await field.focus(); await page.keyboard.press("Tab"); await expect(send).toBeFocused();
    await page.keyboard.press("Shift+Tab"); await expect(field).toBeFocused();
    expect(await field.evaluate(element => getComputedStyle(element).outlineStyle)).not.toBe("none");
    await page.setViewportSize({ width: 480, height: 900 });
    await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
    const geometry = await detail.locator("header").first().evaluate(element => {
      const back = element.querySelector("a")!.getBoundingClientRect(), title = element.querySelector("h2")!.getBoundingClientRect(), refresh = element.querySelector("button")!.getBoundingClientRect();
      return { back: back.toJSON(), title: title.toJSON(), refresh: refresh.toJSON(), overflow: document.documentElement.scrollWidth - innerWidth };
    });
    expect(geometry.back.right).toBeLessThanOrEqual(geometry.title.left);
    expect(geometry.title.right).toBeLessThanOrEqual(geometry.refresh.left);
    expect(geometry.refresh.right).toBeLessThanOrEqual(481);
    expect(geometry.overflow).toBeLessThanOrEqual(1);
    await expect(field).toHaveValue("Preserved keyboard draft");
    await page.screenshot({ path: info.outputPath(`detail-${language}-200percent.png`) });
    expect(state.base.writes).toEqual([]); expect(state.base.base.providerCalls).toEqual([]);
  });

  test(`T17/T18/T25/T31: successful heart updates only the row and retains draft/focus (${language})`, async ({ page }, info) => {
    const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    state.likeDelay = 350;
    await page.goto(detailRoute()); const row = page.locator(`[data-social-post-row="${SYNTHETIC_REPLY}"]`), form = surface(page).locator("form"), field = form.locator("textarea");
    await field.fill("Unsent preserved reply"); await sentinel(row); await sentinel(form); await field.focus();
    const reads = state.gets.length;
    // DOM click leaves input focus in place, exercising the component's update.
    await heart(row).evaluate(element => { (element as HTMLButtonElement).click(); (element as HTMLButtonElement).click(); });
    await expect(heart(row)).toHaveAttribute("aria-busy", "true"); await expect(heart(row)).toBeDisabled();
    await expect(heart(row)).toHaveAttribute("aria-pressed", "true"); await expect(heart(row)).toHaveAccessibleName(language === "ko" ? "좋아요 19" : "Like 19");
    await expect(field).toHaveValue("Unsent preserved reply"); await expect(field).toBeFocused();
    expect(await retained(row)).toBe(true); expect(await retained(form)).toBe(true); expect(state.gets.length).toBe(reads); expect(state.requestCount).toBe(1); expect(await events(page)).toHaveLength(1);
    await expect(surface(page).locator("[data-social-feed-loading]")).toHaveCount(0);
    await heart(row).click(); await expect(heart(row)).toHaveAttribute("aria-pressed", "false"); expect(state.requestCount).toBe(2);
    expect(state.base.base.providerCalls).toEqual([]);
  });

  test(`T21/T23/T29/T30: profile cursor range and ready rows survive canonical refresh failure (${language})`, async ({ page }, info) => {
    const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    await page.goto(profileRoute()); await page.getByRole("tab", { name: language === "ko" ? "좋아요" : "Like", exact: true }).click();
    const activity = page.locator("[data-world-character-social-activity]"), rows = activity.locator("[data-social-post-row]");
    await expect(rows).toHaveCount(10);
    const more = activity.getByRole("button", { name: language === "ko" ? "더 보기" : "More", exact: true });
    await more.click(); await expect(rows).toHaveCount(20); await more.click(); await expect(rows).toHaveCount(30);
    const retainedRow = activity.locator('[data-social-post-row="paged-12"]'); await sentinel(retainedRow);
    state.profileFailure = 503;
    await heart(activity.locator('[data-social-post-row="paged-0"]')).click();
    await expect(heart(activity.locator('[data-social-post-row="paged-0"]'))).toHaveAttribute("aria-pressed", "false");
    await expect(activity.getByRole("alert")).toBeVisible(); await expect(rows).toHaveCount(30); expect(await retained(retainedRow)).toBe(true);
    state.profileFailure = 0; state.profileCounts = { post_count: 101, reply_count: 103, liked_post_count: 29, received_like_count: 107 };
    const readCount = state.gets.length; await activity.getByRole("button", { name: language === "ko" ? "다시 시도" : "Retry", exact: true }).click();
    await expect(activity.locator('[data-social-post-row="paged-0"]')).toHaveCount(0); await expect(rows).toHaveCount(29); expect(await retained(retainedRow)).toBe(true);
    expect(state.gets.slice(readCount).map(read => read.cursor)).toEqual([null, "10", "20"]);
    await expect(page.locator("[data-world-social-profile-metrics]")).toContainText("101");
    await expect(page.locator("[data-world-social-profile-metrics]")).toContainText("107");
  });
}

test("T07/T10: pagination preserves draft and direct reply parent", async ({ page }, info) => {
  const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  for (let index = 0; index < 55; index++) state.base.posts.push({ ...state.base.posts[2], id: `reply-page-${index}`, reply_to_post_id: SYNTHETIC_REPLY });
  await page.goto(detailRoute()); const field = surface(page).locator("form textarea"); await field.fill("Draft across reply pages");
  await surface(page).getByRole("button", { name: "다음 답글", exact: true }).click(); await expect(field).toHaveValue("Draft across reply pages");
  await expect(page.locator('[data-social-post-row="reply-page-54"]')).toBeVisible();
  await surface(page).getByRole("button", { name: "이전 답글", exact: true }).click(); await expect(field).toHaveValue("Draft across reply pages");
  await surface(page).locator('form button[type="submit"]').click(); await expect(field).toHaveValue("");
  expect(state.base.writes.find(write => write.path.endsWith("/replies"))?.path).toContain(`/${SYNTHETIC_REPLY}/replies`);
});

for (const language of ["ko", "en"] as const) test(`T09: reply capability does not create an unauthorized form (${language})`, async ({ page }, info) => {
  const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
  state.base.posts[2].can_owner_reply = false;
  await page.goto(detailRoute("synthetic-leaf"));
  await expect(surface(page).locator("h3")).toBeVisible(); await expect(surface(page).locator("form")).toHaveCount(0);
  await expect(surface(page).locator("textarea")).toHaveCount(0); expect(state.base.writes).toEqual([]);
});

test("T10: failed reply keeps draft and reuses its key for an explicit retry", async ({ page }, info) => {
  const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  state.base.replyFailures = 1;
  await page.goto(detailRoute()); const form = surface(page).locator("form"), field = form.locator("textarea"), send = form.locator('button[type="submit"]');
  await field.fill("Synthetic retry draft"); await send.click();
  await expect(surface(page).getByRole("alert")).toBeVisible(); await expect(field).toHaveValue("Synthetic retry draft"); await expect(send).toBeEnabled();
  const writes = () => state.base.writes.filter(write => write.path.endsWith("/replies"));
  expect(writes()).toHaveLength(1); const firstKey = writes()[0].key; expect(firstKey).toBeTruthy();
  await send.click(); await expect(field).toHaveValue(""); expect(writes()).toHaveLength(2);
  expect(writes()[1].key).toBe(firstKey); expect(writes()[1].path).toContain(`/${SYNTHETIC_REPLY}/replies`);
  expect(state.base.base.providerCalls).toEqual([]);
});

for (const failure of [403, 503, "malformed"] as const) test(`T23/T24: failed or unconfirmed mutation keeps state (${failure})`, async ({ page }, info) => {
  const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  if (failure === "malformed") state.corruptLike = true; else state.likeFailure = failure;
  await page.goto(detailRoute()); const row = page.locator(`[data-social-post-row="${SYNTHETIC_REPLY}"]`); await sentinel(row);
  const reads = state.gets.length; await heart(row).click(); await expect(surface(page).getByRole("alert")).toBeVisible();
  await expect(heart(row)).toHaveAttribute("aria-pressed", "false"); await expect(heart(row)).toBeEnabled();
  expect(await retained(row)).toBe(true); expect(state.gets.length).toBe(reads); expect(await events(page)).toEqual([]); expect(state.requestCount).toBe(1);
});

test("T22: another character's likes membership is independent of viewer unlike", async ({ page }, info) => {
  const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(`/worlds/${FEED_WORLD}/characters/synthetic-responder`); await page.getByRole("tab", { name: "좋아요", exact: true }).click();
  const activity = page.locator('[data-world-character-social-activity]');
  await expect(activity).toHaveAttribute("data-world-character-social-tab", "likes");
  await expect(activity.locator('[data-social-post-row]')).toHaveCount(10);
  const row = activity.locator('[data-social-post-row="paged-0"]'); await sentinel(row); const reads = state.gets.length; await heart(row).click();
  await expect(heart(row)).toHaveAttribute("aria-pressed", "false"); await expect.poll(() => state.gets.length).toBeGreaterThan(reads);
  await expect(row).toBeVisible(); expect(await retained(row)).toBe(true); expect(state.otherLikes.has("paged-0")).toBe(true);
});

test("T26: delayed profile load-more does not overwrite a newer confirmed heart", async ({ page }, info) => {
  const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(profileRoute()); await page.getByRole("tab", { name: "좋아요", exact: true }).click();
  const activity = page.locator("[data-world-character-social-activity]"); await expect(activity.locator("[data-social-post-row]")).toHaveCount(10);
  state.getDelay = 500; await activity.getByRole("button", { name: "더 보기", exact: true }).click();
  const row = activity.locator('[data-social-post-row="paged-0"]'); await heart(row).click(); await expect(heart(row)).toHaveAttribute("aria-pressed", "false");
  await expect(activity.locator('[data-social-post-row="paged-0"]')).toHaveCount(0); await expect(activity.locator("[data-social-post-row]")).toHaveCount(20);
  expect(state.requestCount).toBe(1);
});

test("T27: late mutation after route change does not publish into the new detail", async ({ page }, info) => {
  const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL)); state.likeDelay = 700;
  await page.goto(detailRoute()); await heart(page.locator(`[data-social-post-row="${SYNTHETIC_REPLY}"]`)).click();
  await page.getByRole("link", { name: "부모 게시글 보기", exact: true }).first().click();
  const root = page.locator(`[data-social-post-row="${SYNTHETIC_ROOT}"]`); await expect(root).toBeVisible();
  await expect.poll(() => state.base.posts[1].viewer_like_state).toBe("liked"); await expect(heart(root)).toHaveAttribute("aria-pressed", "false"); expect(await events(page)).toEqual([]);
});

test("T19: global feed retains all three loaded pages and cursor after unlike", async ({ page }, info) => {
  const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.setViewportSize({ width: 960, height: 900 }); await page.goto("/posts");
  await page.getByRole("button", { name: "새로고침", exact: true }).click();
  const rows = page.locator("[data-social-post-row]"); await expect(rows).toHaveCount(10);
  const scroll = async () => page.evaluate(() => { const owner = document.querySelector<HTMLElement>('[data-device-scroll-owner="true"]')!; owner.scrollTop = owner.scrollHeight; owner.dispatchEvent(new Event("scroll")); });
  await scroll(); await expect(rows).toHaveCount(20); await scroll(); await expect(rows).toHaveCount(30);
  const ids = await rows.evaluateAll(elements => elements.map(element => (element as HTMLElement).dataset.socialPostRow));
  const row = page.locator('[data-social-post-row="paged-15"]'); await sentinel(row);
  const reads = state.gets.length; await heart(row).click(); await expect(heart(row)).toHaveAttribute("aria-pressed", "false");
  expect(await rows.evaluateAll(elements => elements.map(element => (element as HTMLElement).dataset.socialPostRow))).toEqual(ids);
  expect(state.gets.length).toBe(reads); expect(await retained(row)).toBe(true); expect(state.requestCount).toBe(1);
});

test("T20/T26: global detail applies exact root/reply and fences an older GET", async ({ page }, info) => {
  const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(`/posts/${SYNTHETIC_ROOT}`);
  await page.getByRole("button", { name: "새로고침", exact: true }).click();
  const root = page.locator(`[data-social-post-row="${SYNTHETIC_ROOT}"]`), reply = page.locator(`[data-social-post-row="${SYNTHETIC_REPLY}"]`);
  await expect(root).toBeVisible(); await expect(heart(root)).toHaveAttribute("aria-pressed", "false");
  await sentinel(root); const reads = state.gets.length;
  await heart(root).click(); await expect.poll(() => state.requestCount).toBe(1); await expect.poll(async () => (await events(page)).length).toBe(1);
  await expect(heart(root)).toHaveAttribute("aria-pressed", "true");
  await heart(reply).click(); await expect(heart(reply)).toHaveAttribute("aria-pressed", "true");
  expect(state.gets.length).toBe(reads); expect(await retained(root)).toBe(true);
  state.getDelay = 550; await page.getByRole("button", { name: "새로고침", exact: true }).click();
  state.likeCount = 37; await heart(root).click(); await expect(heart(root)).toHaveAttribute("aria-pressed", "false");
  await expect(heart(root)).toHaveAccessibleName("좋아요 37");
  await expect(page.getByText("게시글을 불러오는 중", { exact: true })).toHaveCount(0);
  await expect(heart(root)).toHaveAttribute("aria-pressed", "false"); await expect(heart(root)).toHaveAccessibleName("좋아요 37");
});

test("T17: World feed preserves image, scroll and media request identity", async ({ page }, info) => {
  const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  state.base.posts[0].media = [{ id: 1, post_id: SYNTHETIC_ROOT, media_type: "image", url: "/media/synthetic-preserved.png", alt_text: "Synthetic preserved image", width: 1, height: 1 }];
  let imageRequests = 0;
  await page.route("**/media/synthetic-preserved.png", route => { imageRequests++; return route.fulfill({ contentType: "image/png", body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9XcAAAAASUVORK5CYII=", "base64") }); });
  await page.goto(feedRoute()); const row = page.locator(`[data-social-post-row="${SYNTHETIC_ROOT}"]`), image = row.getByRole("img", { name: "Synthetic preserved image" });
  await image.scrollIntoViewIfNeeded(); await expect.poll(() => image.evaluate(element => (element as HTMLImageElement).naturalWidth)).toBe(1);
  await sentinel(row); await sentinel(image);
  const scroll = () => page.locator('[data-device-scroll-owner="true"]').evaluate(element => element.scrollTop);
  const before = await scroll(), reads = state.gets.length, requests = imageRequests;
  await heart(row).evaluate(element => (element as HTMLButtonElement).click()); await expect(heart(row)).toHaveAttribute("aria-pressed", "true");
  expect(await retained(row)).toBe(true); expect(await retained(image)).toBe(true); expect(await scroll()).toBe(before);
  expect(imageRequests).toBe(requests); expect(state.gets.length).toBe(reads);
});

test("T21/T23: removal preserves an adjacent visible anchor and existing focus", async ({ page }, info) => {
  const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(profileRoute()); await page.getByRole("tab", { name: "좋아요", exact: true }).click();
  const activity = page.locator("[data-world-character-social-activity]"), more = activity.getByRole("button", { name: "더 보기", exact: true });
  await more.click(); await expect(activity.locator("[data-social-post-row]")).toHaveCount(20); await more.click(); await expect(activity.locator("[data-social-post-row]")).toHaveCount(30);
  const anchor = activity.locator('[data-social-post-row="paged-15"]'); await heart(anchor).focus(); await anchor.scrollIntoViewIfNeeded();
  const top = (await anchor.boundingBox())!.y;
  await heart(activity.locator('[data-social-post-row="paged-0"]')).evaluate(element => (element as HTMLButtonElement).click());
  await expect(activity.locator('[data-social-post-row="paged-0"]')).toHaveCount(0);
  await expect(heart(anchor)).toBeFocused(); expect(Math.abs((await anchor.boundingBox())!.y - top)).toBeLessThanOrEqual(2); expect(state.requestCount).toBe(1);
});

test("T11/T31/T32: locale change during a like preserves pending identity and emits no credentials", async ({ page }, info) => {
  const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL)); state.likeDelay = 500;
  await page.goto(detailRoute()); const row = page.locator(`[data-social-post-row="${SYNTHETIC_REPLY}"]`), form = surface(page).locator("form");
  await form.locator("textarea").fill("Untranslated draft"); await heart(row).click();
  state.base.base.language = "en"; await page.evaluate(() => window.dispatchEvent(new Event("angmoo:auth-changed")));
  await expect(surface(page).getByRole("heading", { name: "post", exact: true })).toBeVisible(); await expect(heart(row)).toHaveAttribute("aria-pressed", "true");
  await expect(form.locator("textarea")).toHaveValue("Untranslated draft"); expect(state.requestCount).toBe(1);
  expect(Object.keys((await events(page))[0] as object).sort()).toEqual(["world_id", "post_id", "owner_world_character_id", "viewer_like_state", "like_count", "can_owner_like", "revision"].sort());
});

test("T27: auth replacement during mutation suppresses the old success event", async ({ page }, info) => {
  const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL)); state.likeDelay = 600;
  await page.goto(detailRoute()); await heart(page.locator(`[data-social-post-row="${SYNTHETIC_REPLY}"]`)).click();
  await page.evaluate(() => { const user = JSON.parse(sessionStorage.getItem("angmoo.user")!); sessionStorage.setItem("angmoo.user", JSON.stringify({ ...user, id: "replacement-owner" })); window.dispatchEvent(new Event("angmoo:auth-changed")); });
  await expect.poll(() => state.base.posts[1].viewer_like_state).toBe("liked"); expect(await events(page)).toEqual([]);
});

for (const change of ["logout", "runtime", "tab"] as const) test(`T27: pending mutation is retired after ${change}`, async ({ page }, info) => {
  const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL)); state.likeDelay = 600;
  if (change === "tab") {
    await page.goto(profileRoute()); await page.getByRole("tab", { name: "좋아요", exact: true }).click();
    const activity = page.locator("[data-world-character-social-activity]");
    await expect(activity.locator("[data-social-post-row]")).toHaveCount(10);
    await heart(activity.locator('[data-social-post-row="paged-0"]')).click();
    await page.getByRole("tab", { name: "게시글", exact: true }).click();
    await expect(activity).toHaveAttribute("data-world-character-social-tab", "posts");
    await expect.poll(() => state.base.posts.find(post => post.id === "paged-0")!.viewer_like_state).toBe("not_liked");
  } else {
    await page.goto(detailRoute()); await heart(page.locator(`[data-social-post-row="${SYNTHETIC_REPLY}"]`)).click();
    if (change === "logout") await page.evaluate(() => {
      sessionStorage.removeItem("angmoo.token"); sessionStorage.removeItem("angmoo.user"); window.dispatchEvent(new Event("angmoo:auth-changed"));
    });
    else await page.evaluate(() => {
      Object.assign(window, { __ANGMOO_RUNTIME_CONFIG__: { profile: "tauri-static", apiBaseUrl: "http://127.0.0.1:8081", graphProvider: "ladybug", launchToken: "replacement-synthetic-runtime-token-00000000" } });
      window.dispatchEvent(new Event("angmoo:desktop-runtime-config-changed"));
    });
    await expect.poll(() => state.base.posts[1].viewer_like_state).toBe("liked");
  }
  expect(await events(page)).toEqual([]); expect(state.requestCount).toBe(1); expect(state.base.base.providerCalls).toEqual([]);
});

test("T26: an explicit World GET begun before success cannot restore the old heart", async ({ page }, info) => {
  const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(detailRoute()); const row = page.locator(`[data-social-post-row="${SYNTHETIC_REPLY}"]`); await expect(row).toBeVisible();
  state.likeDelay = 350; state.getDelay = 650;
  await heart(row).click(); await surface(page).getByRole("button", { name: "새로고침", exact: true }).click();
  await expect(heart(row)).toHaveAttribute("aria-pressed", "true"); await expect(heart(row)).toHaveAccessibleName("좋아요 19");
  expect(state.requestCount).toBe(1); expect(await events(page)).toHaveLength(1);
});

test("T08: detail back and refresh preserve the real World route and existing read", async ({ page }, info) => {
  const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(detailRoute());
  const header = surface(page).locator(":scope > header");
  await expect(page.locator(`[data-social-post-row="${SYNTHETIC_REPLY}"]`)).toBeVisible();
  await expect(header).toHaveCount(1);
  const reads = state.gets.length;
  await header.getByRole("button", { name: "새로고침", exact: true }).click();
  await expect.poll(() => state.gets.length).toBe(reads + 1);
  expect(state.gets.at(-1)?.path).toContain(`/manual-social/posts/${SYNTHETIC_REPLY}`);
  await header.getByRole("link").click();
  await expect(page).toHaveURL(new RegExp(`/worlds/${FEED_WORLD}/feed/?$`));
  await expect(page.locator('[data-world-social-surface="feed"]')).toBeVisible();
  expect(state.base.base.providerCalls).toEqual([]);
});

test("T25: separate posts retain independent pending locks and exact counts", async ({ page }, info) => {
  const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  state.likeDelay = 650;
  await page.goto(detailRoute());
  const first = page.locator(`[data-social-post-row="${SYNTHETIC_REPLY}"]`), second = page.locator('[data-social-post-row="synthetic-leaf"]');
  await heart(first).click();
  await expect(heart(first)).toBeDisabled(); await expect(heart(second)).toBeEnabled();
  await heart(second).click(); await expect(heart(second)).toBeDisabled();
  await expect(heart(first)).toHaveAttribute("aria-pressed", "true"); await expect(heart(second)).toHaveAttribute("aria-pressed", "true");
  await expect(heart(first)).toHaveAccessibleName("좋아요 19"); await expect(heart(second)).toHaveAccessibleName("좋아요 19");
  expect(state.requestCount).toBe(2); expect(await events(page)).toHaveLength(2);
});

for (const status of [401, 403, 404]) test(`T30: authoritative background access loss removes restricted rows (${status})`, async ({ page }, info) => {
  const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(profileRoute()); await page.getByRole("tab", { name: "좋아요", exact: true }).click();
  const activity = page.locator('[data-world-character-social-activity]');
  await expect(activity.locator('[data-social-post-row]')).toHaveCount(10);
  state.profileFailure = status; const reads = state.gets.length;
  await heart(activity.locator('[data-social-post-row="paged-0"]')).click();
  await expect(activity.locator('[data-social-post-row]')).toHaveCount(0);
  if (status === 401) {
    await expect.poll(() => page.evaluate(() => sessionStorage.getItem("angmoo.user"))).toBeNull();
    await expect(page.getByRole("heading", { name: "로컬 owner 연결이 필요해요", exact: true })).toBeVisible();
  }
  else await expect(activity.getByText("이 활동을 볼 수 없어요", { exact: true })).toBeVisible();
  const scopedReads = state.gets.length - reads;
  expect(scopedReads).toBeGreaterThanOrEqual(1);
  expect(scopedReads).toBeLessThanOrEqual(status === 401 ? 2 : 1);
  expect(state.requestCount).toBe(1);
});

test("T23/T31: English failed like remains retryable with untranslated draft", async ({ page }, info) => {
  const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), "en");
  state.likeFailure = 503;
  await page.goto(detailRoute());
  const row = page.locator(`[data-social-post-row="${SYNTHETIC_REPLY}"]`), field = surface(page).locator("form textarea");
  await field.fill("Original English unsent draft"); await heart(row).click();
  await expect(surface(page).getByRole("alert")).toContainText("Could not save your like");
  await expect(heart(row)).toHaveAccessibleName("Like 0"); await expect(heart(row)).toBeEnabled();
  await expect(field).toHaveValue("Original English unsent draft");
  state.likeFailure = 0; await heart(row).click(); await expect(heart(row)).toHaveAccessibleName("Like 19");
  expect(state.requestCount).toBe(2); expect(await events(page)).toHaveLength(1);
});

test("T24: a stored like with a lost response stays unconfirmed until explicit GET", async ({ page }, info) => {
  const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  state.loseLikeResponse = true;
  await page.goto(detailRoute()); const row = page.locator(`[data-social-post-row="${SYNTHETIC_REPLY}"]`);
  await expect(heart(row)).toBeVisible(); const reads = state.gets.length;
  await heart(row).click(); await expect(surface(page).getByRole("alert")).toBeVisible();
  await expect(heart(row)).toHaveAttribute("aria-pressed", "false");
  expect(state.base.posts[1].viewer_like_state).toBe("liked"); expect(state.requestCount).toBe(1);
  expect(state.gets.length).toBe(reads); expect(await events(page)).toEqual([]);
  await surface(page).getByRole("button", { name: "새로고침", exact: true }).click();
  await expect(heart(row)).toHaveAttribute("aria-pressed", "true"); await expect(heart(row)).toHaveAccessibleName("좋아요 19");
  expect(state.requestCount).toBe(1);
});

test("T22: newly included profile likes arrive only through complete canonical GET rows", async ({ page }, info) => {
  const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(profileRoute()); await page.getByRole("tab", { name: "좋아요", exact: true }).click();
  const activity = page.locator('[data-world-character-social-activity]');
  await expect(activity.locator('[data-social-post-row]')).toHaveCount(10);
  const readCount = state.gets.length;
  state.base.posts.unshift({ ...state.base.posts.find(post => post.id === "paged-0")!, id: "canonical-new-liked",
    title: "Canonical inserted title", body: "Complete canonical inserted body", viewer_like_state: "liked", like_count: 29 });
  await heart(activity.locator('[data-social-post-row="paged-0"]')).click();
  const added = activity.locator('[data-social-post-row="canonical-new-liked"]');
  await expect(added.locator("p")).toContainText("Complete canonical inserted body");
  await expect(added).toContainText("Canonical inserted title");
  await expect(heart(added)).toHaveAttribute("aria-pressed", "true");
  await expect(heart(added)).toHaveAccessibleName("좋아요 29");
  expect(state.gets.length).toBeGreaterThan(readCount); expect(await events(page)).toHaveLength(1);
  expect((await events(page))[0]).not.toHaveProperty("body");
});

test("T29: canonical count refresh retains all loaded posts rows without local aggregate arithmetic", async ({ page }, info) => {
  const state = await installPostReactionFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(`/worlds/${FEED_WORLD}/characters/synthetic-responder`);
  const activity = page.locator('[data-world-character-social-activity]'), rows = activity.locator('[data-social-post-row]');
  await expect(rows).toHaveCount(10); const more = activity.getByRole("button", { name: "더 보기", exact: true });
  await more.click(); await expect(rows).toHaveCount(20); await more.click(); await expect(rows).toHaveCount(30);
  const ids = await rows.evaluateAll(elements => elements.map(element => (element as HTMLElement).dataset.socialPostRow));
  const row = activity.locator('[data-social-post-row="paged-12"]'); await sentinel(row);
  state.profileCounts = { post_count: 111, reply_count: 113, liked_post_count: 117, received_like_count: 119 };
  await heart(row).click();
  await expect(page.locator('[data-world-social-profile-metrics]')).toContainText("119");
  expect(await rows.evaluateAll(elements => elements.map(element => (element as HTMLElement).dataset.socialPostRow))).toEqual(ids);
  expect(await retained(row)).toBe(true); expect(state.requestCount).toBe(1);
});
