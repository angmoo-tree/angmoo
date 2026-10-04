import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { FEED_WORLD, OTHER_FEED_WORLD, OWNER_NAME, OWNER_HANDLE, feedRoute, profileRoute, installWorldFeedFixture } from "./world-feed-fixture";
import { uiDManualPost } from "./continuity-next-fixture";

const composer = (page: Page) => page.locator("#world-owner-composer");
const title = (page: Page) => composer(page).locator("input[type=text], input:not([type])");
const body = (page: Page) => composer(page).locator("textarea");
const publish = (page: Page) => composer(page).locator("button[type=submit]");
const photo = (page: Page) => composer(page).getByRole("button", { name: /사진 첨부|Attach photo/ });
const profileHref = (info: TestInfo, world = FEED_WORLD) => `${profileRoute(world)}${info.project.name === "static-export" ? "/" : ""}`;
async function fill(page: Page, heading = "Synthetic title", content = "Synthetic body") { await title(page).fill(heading); await body(page).fill(content); }
const synthetic = (extension: string, mime: string) => ({ name: `fixture.${extension}`, mimeType: mime,
  buffer: readFileSync(`../backend/tests/image_integration/fixtures/pixels.${extension}`) });
async function expectActionSizes(page: Page) {
  const boxes = await composer(page).locator('button[type="submit"], button[title="사진 첨부"], button[title="사진을 업로드하고 확인하는 중…"]').all();
  expect(boxes).toHaveLength(2);
  for (const action of boxes) { const rect = await action.boundingBox(); expect(rect!.width).toBe(48); expect(rect!.height).toBe(48); }
}

for (const language of ["ko", "en"] as const) test(`header owner and icon-only composer keep names and real profile route (${language})`, async ({ page }, info) => {
  const audit = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
  await page.goto(feedRoute()); await expect(composer(page)).toBeVisible();
  const header = page.locator("[data-feed-header]");
  await expect(header.getByRole("heading", { name: language === "ko" ? "피드" : "Feed", exact: true })).toBeVisible();
  await expect(header.getByRole("link", { name: language === "ko" ? "내 프로필" : "My Profile", exact: true })).toHaveAttribute("href", profileHref(info));
  await expect(header.getByRole("link", { name: "Angmoo", exact: true })).toHaveAttribute("href", "/");
  await expect(header.locator("button")).toHaveCount(0);
  await expect(page.getByText(uiWorldName(), { exact: true })).toHaveCount(0);
  await expect(page.getByText(/WORLD FEED|WORLD APP|provider 호출 없음|이 World의 이야기/)).toHaveCount(0);
  await expect(page.getByRole("tab")).toHaveCount(0);
  await expect(composer(page).getByText(OWNER_NAME, { exact: true })).toBeVisible();
  await expect(composer(page).getByText(`@${OWNER_HANDLE}`, { exact: true })).toBeVisible();
  await expect(title(page)).toHaveAttribute("maxlength", "160"); await expect(body(page)).toHaveAttribute("maxlength", "4000");
  await expect(title(page)).toHaveAccessibleName(language === "ko" ? "제목" : "Title");
  await expect(body(page)).toHaveAccessibleName(language === "ko" ? "내용" : "Body");
  await expect(publish(page)).toHaveAccessibleName(language === "ko" ? "게시하기" : "Publish post");
  await expect(publish(page)).toHaveText(""); await expect(photo(page)).toHaveText("");
  await expect(publish(page)).toBeDisabled(); await expect(photo(page)).toBeEnabled();
  const positions = await Promise.all([photo(page).boundingBox(), publish(page).boundingBox()]);
  for (const rect of positions) { expect(rect!.width).toBe(48); expect(rect!.height).toBe(48); }
  expect(positions[0]!.x).toBeLessThan(positions[1]!.x); expect(positions[0]!.y).toBe(positions[1]!.y);
  await expect(page.locator("[data-device-scroll-owner=true]")).toHaveCount(1);
  await header.getByRole("link", { name: language === "ko" ? "내 프로필" : "My Profile", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`${profileRoute()}/?$`));
  expect(audit.writes).toEqual([]); expect(audit.providerCalls).toEqual([]);
});

function uiWorldName() { return "UI-D Social World"; }

test("title and body stay required and one in-flight submit preserves the actual payload", async ({ page }, info) => {
  const audit = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  audit.postDelay = 700; await page.goto(feedRoute()); await fill(page, "Actual title", "Actual body");
  await title(page).fill(" "); await expect(publish(page)).toBeDisabled(); await title(page).fill("Actual title");
  await body(page).fill(" "); await expect(publish(page)).toBeDisabled(); await body(page).fill("Actual body");
  await publish(page).click(); await expect(publish(page)).toBeDisabled(); await expect(publish(page)).toHaveAttribute("aria-busy", "true");
  await expect(title(page)).toHaveAttribute("readonly", ""); await expect(body(page)).toHaveAttribute("readonly", "");
  await expectActionSizes(page);
  await expect(title(page)).toHaveValue(""); await expect(body(page)).toHaveValue("");
  const writes = audit.writes.filter(write => write.path.endsWith("/manual-social/posts"));
  expect(writes).toHaveLength(1); expect(writes[0].body).toEqual({ title: "Actual title", body: "Actual body" });
  expect(audit.writes).toHaveLength(1);
  await expect(page.locator('[data-social-post-row="created-1"]')).toContainText("Actual title");
  expect(audit.providerCalls).toEqual([]);
});

test("failed submission keeps text and attachment and reuses the same idempotency key", async ({ page }, info) => {
  const audit = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  audit.postFailures = 1; await page.goto(feedRoute()); await fill(page);
  await composer(page).locator('input[type="file"]').setInputFiles(synthetic("jpg", "image/jpeg"));
  await expect(composer(page).getByRole("button", { name: "사진 제거" })).toBeVisible();
  await publish(page).click(); await expect(page.getByText("다른 활동을 저장하는 중입니다. 같은 요청으로 다시 시도해주세요.")).toBeVisible();
  await expect(title(page)).toHaveValue("Synthetic title"); await expect(body(page)).toHaveValue("Synthetic body");
  await expect(composer(page).getByRole("img", { name: "선택한 첨부 이미지 미리보기" })).toBeVisible();
  await publish(page).click(); await expect(title(page)).toHaveValue("");
  const writes = audit.writes.filter(write => write.path.endsWith("/manual-social/posts"));
  expect(writes).toHaveLength(2); expect(writes[0].key).toBe(writes[1].key);
  expect(writes[1].body).toEqual({ title: "Synthetic title", body: "Synthetic body", attachment_asset_id: "draft-1" });
  expect(audit.posts).toHaveLength(1); expect(audit.discarded).toEqual([]);
});

for (const [extension, mime] of [["png", "image/png"], ["jpg", "image/jpeg"], ["webp", "image/webp"]]) test(`${extension} preview, publication and reload preserve pixels and authenticated media`, async ({ page }, info) => {
  const audit = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(feedRoute()); await fill(page); await composer(page).locator('input[type="file"]').setInputFiles(synthetic(extension, mime));
  const preview = composer(page).getByRole("img", { name: "선택한 첨부 이미지 미리보기" });
  await expect(preview).toBeVisible();
  await expect.poll(() => preview.evaluate(img => (img as HTMLImageElement).naturalWidth)).toBe(18);
  const uploaded = audit.writes.find(write => write.path === "/media/assets")!.body!;
  expect(uploaded.content_type).toBe(mime); expect(Buffer.from(String(uploaded.data_base64), "base64")).toEqual(synthetic(extension, mime).buffer);
  await publish(page).click(); await expect(page.locator('[data-social-post-row="created-1"] img')).toBeVisible();
  await page.reload(); const image = page.locator('[data-social-post-row="created-1"] img'); await expect(image).toBeVisible();
  await expect.poll(() => image.evaluate(img => (img as HTMLImageElement).naturalWidth)).toBe(18);
  expect(audit.writes.filter(write => write.path.endsWith("/manual-social/posts"))).toHaveLength(1);
  expect(audit.providerCalls).toEqual([]);
});

test("photo replacement and removal discard only old drafts and an upload failure stays editable", async ({ page }, info) => {
  const audit = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(feedRoute()); await fill(page);
  const input = composer(page).locator('input[type="file"]');
  await input.setInputFiles(synthetic("png", "image/png")); await expect(composer(page).getByRole("button", { name: "사진 제거" })).toBeVisible();
  await input.setInputFiles(synthetic("webp", "image/webp")); await expect.poll(() => audit.discarded).toEqual(["draft-1"]);
  await composer(page).getByRole("button", { name: "사진 제거" }).click(); await expect.poll(() => audit.discarded).toEqual(["draft-1", "draft-2"]);
  audit.uploadFailures = 1; await input.setInputFiles(synthetic("jpg", "image/jpeg"));
  await expect(composer(page).locator('[data-ui-primitive="inline-error"]')).toBeVisible();
  await expect(photo(page)).toBeEnabled(); await expect(publish(page)).toBeEnabled();
  await expect(title(page)).toHaveValue("Synthetic title"); expect(audit.providerCalls).toEqual([]);
});

test("upload pending disables photo and publication with an accessible busy name", async ({ page }, info) => {
  const audit = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  audit.uploadDelay = 700; await page.goto(feedRoute()); await fill(page);
  await composer(page).locator('input[type="file"]').setInputFiles(synthetic("png", "image/png"));
  await expect(publish(page)).toBeDisabled();
  const busyPhoto = composer(page).locator('button[aria-busy="true"]');
  await expect(busyPhoto).toHaveAccessibleName("사진을 업로드하고 확인하는 중…"); await expect(busyPhoto).toBeDisabled();
  await expectActionSizes(page);
  await expect(composer(page).getByRole("img", { name: "선택한 첨부 이미지 미리보기" })).toBeVisible(); await expect(publish(page)).toBeEnabled();
});

test("feed failure has explicit retry with retained draft and no header refresh button", async ({ page }, info) => {
  const audit = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  audit.feedFailures = 1; await page.goto(feedRoute()); await fill(page);
  await page.getByRole("button", { name: "다시 시도", exact: true }).click();
  await expect(page.getByRole("button", { name: "다시 시도", exact: true })).toHaveCount(0);
  await expect(title(page)).toHaveValue("Synthetic title"); await expect(body(page)).toHaveValue("Synthetic body");
  await expect(page.locator("[data-feed-header] button")).toHaveCount(0);
  expect(audit.reads.filter(path => path.endsWith("/manual-social/feed"))).toHaveLength(2); expect(audit.writes).toEqual([]);
});

test("pull refresh retains draft and attachment without using a hidden header action", async ({ page }, info) => {
  await page.addInitScript(() => { Object.defineProperty(window, "ontouchstart", { value: null, configurable: true }); });
  const audit = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(feedRoute()); await fill(page);
  await composer(page).locator('input[type="file"]').setInputFiles(synthetic("webp", "image/webp"));
  const preview = composer(page).getByRole("img", { name: "선택한 첨부 이미지 미리보기" });
  await expect(preview).toBeVisible();
  const previewSource = await preview.getAttribute("src");
  const before = audit.reads.filter(path => path.endsWith("/manual-social/feed")).length;
  await page.locator("[data-feed-header] h1").evaluate(target => {
    const touch = (y: number) => new Touch({ identifier: 1, target, clientX: 30, clientY: y });
    target.dispatchEvent(new TouchEvent("touchstart", { bubbles: true, touches: [touch(10)] }));
    target.dispatchEvent(new TouchEvent("touchmove", { bubbles: true, cancelable: true, touches: [touch(100)] }));
    target.dispatchEvent(new TouchEvent("touchend", { bubbles: true, touches: [] }));
  });
  await expect.poll(() => audit.reads.filter(path => path.endsWith("/manual-social/feed")).length).toBe(before + 1);
  await expect(title(page)).toHaveValue("Synthetic title"); await expect(body(page)).toHaveValue("Synthetic body");
  await expect(preview).toBeVisible(); await expect(preview).toHaveAttribute("src", previewSource!);
  expect(audit.writes.filter(write => write.path === "/media/assets")).toHaveLength(1);
  expect(audit.writes.filter(write => write.path.endsWith("/manual-social/posts"))).toEqual([]);
  expect(audit.discarded).toEqual([]);
});

test("World identity changes and absent avatar use the actual owner, never a global agent", async ({ page }, info) => {
  const audit = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  audit.avatar = false; await page.goto(feedRoute()); await expect(composer(page)).toContainText(OWNER_NAME);
  await expect(page.locator("[data-feed-header] img[alt$='프로필 이미지']")).toHaveCount(0);
  await page.goto(feedRoute(OTHER_FEED_WORLD)); await expect(composer(page)).toContainText("Other World User");
  await expect(page.locator("[data-feed-header]").getByRole("link", { name: "내 프로필" })).toHaveAttribute("href", profileHref(info, OTHER_FEED_WORLD));
  expect(audit.ownerReads[FEED_WORLD]).toBe(1); expect(audit.ownerReads[OTHER_FEED_WORLD]).toBe(1); expect(audit.writes).toEqual([]);
});

test("missing owner is ensured once after an authorized World read; read errors never borrow the global agent", async ({ page }, info) => {
  const audit = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  audit.missingOwner = true; audit.avatar = false; audit.handle = null;
  await page.goto(feedRoute()); await expect(composer(page)).toContainText(OWNER_NAME);
  await expect(composer(page).getByText(`@${OWNER_HANDLE}`, { exact: true })).toHaveCount(0);
  expect(audit.writes.map(write => write.path)).toEqual([`/worlds/${FEED_WORLD}/my-profile/ensure`]);
  const header = page.locator("[data-feed-header]");
  await expect(header.getByRole("link", { name: "내 프로필" })).toContainText("S");
  await expect(header).not.toContainText(audit.globalName);
  audit.ownerFailures = 1; await page.reload();
  await expect(page.getByRole("heading", { name: "World 앱을 불러오지 못했어요", exact: true })).toBeVisible();
  await expect(composer(page)).toHaveCount(0); await expect(page.locator("[data-feed-header]")).toHaveCount(0);
  expect(audit.writes).toHaveLength(1); expect(audit.providerCalls).toEqual([]);
});

test("unavailable World with no owner does not trigger profile creation", async ({ page }, info) => {
  const audit = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  audit.worldForbidden = true; audit.missingOwner = true; await page.goto(feedRoute());
  await expect(page.getByRole("heading", { name: "이 World 앱을 열 수 없어요", exact: true })).toBeVisible();
  await expect(composer(page)).toHaveCount(0); expect(audit.writes).toEqual([]);
});

test("late World A owner response cannot replace World B profile or composer", async ({ page }, info) => {
  const audit = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  audit.ownerDelays[FEED_WORLD] = 700; await page.goto(feedRoute());
  await expect.poll(() => audit.ownerReads[FEED_WORLD]).toBe(1);
  await page.goto(feedRoute(OTHER_FEED_WORLD)); await expect(composer(page)).toContainText("Other World User");
  await expect.poll(() => audit.ownerResponses.includes(FEED_WORLD)).toBe(true);
  await expect(composer(page)).not.toContainText(OWNER_NAME);
  await expect(page.locator("[data-feed-header]").getByRole("link", { name: "내 프로필" })).toHaveAttribute("href", profileHref(info, OTHER_FEED_WORLD));
  await fill(page); await publish(page).click();
  expect(audit.writes.filter(write => write.path.endsWith("/manual-social/posts")).map(write => write.path))
    .toEqual([`/worlds/${OTHER_FEED_WORLD}/manual-social/posts`]);
});

test("profile edit and return refresh the same World header and composer identity", async ({ page }, info) => {
  const audit = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(feedRoute()); await expect(composer(page)).toBeVisible();
  await page.locator("[data-feed-header]").getByRole("link", { name: "내 프로필" }).click();
  await page.getByRole("button", { name: "내 프로필 편집", exact: true }).click();
  const editor = page.getByRole("region", { name: "내 프로필 편집", exact: true });
  await editor.getByRole("textbox", { name: "이름", exact: true }).fill("Edited World User");
  await editor.getByRole("textbox", { name: "핸들", exact: true }).fill("edited_world_user");
  await editor.getByRole("button", { name: "프로필 저장", exact: true }).click();
  // Saving reloads the parent profile and remounts the editor. Verify the
  // durable edit result rather than its transient, unmounted notice.
  await expect.poll(() => audit.displayName).toBe("Edited World User");
  await expect(page.getByRole("heading", { name: "Edited World User", exact: true })).toBeVisible();
  await page.getByRole("navigation", { name: "World 앱 기능" }).getByRole("link", { name: "Feed", exact: true }).click();
  await expect(composer(page)).toContainText("Edited World User"); await expect(composer(page)).toContainText("@edited_world_user");
  await expect(page.locator("[data-feed-header]").getByRole("img", { name: "Edited World User 프로필 이미지", exact: true })).toBeVisible();
  expect(audit.writes.filter(write => write.method === "PATCH")).toHaveLength(1);
  expect(audit.ownerReads[FEED_WORLD]).toBeGreaterThan(1); expect(audit.providerCalls).toEqual([]);
});

test("photo trigger opens one native chooser, cancellation and cancelled navigation retain the draft", async ({ page }, info) => {
  const audit = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(feedRoute()); await fill(page);
  await composer(page).locator('input[type="file"]').setInputFiles(synthetic("png", "image/png"));
  await expect(composer(page).getByRole("button", { name: "사진 제거" })).toBeVisible();
  const chooserPromise = page.waitForEvent("filechooser"); await photo(page).click();
  const chooser = await chooserPromise; expect(chooser.isMultiple()).toBe(false); await chooser.setFiles([]);
  await expect(composer(page).locator('input[type="file"]')).toHaveCount(1);
  await expect(composer(page).getByRole("img", { name: "선택한 첨부 이미지 미리보기" })).toBeVisible();
  page.once("dialog", dialog => dialog.dismiss());
  await page.locator("[data-feed-header]").getByRole("link", { name: "Angmoo", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`${feedRoute()}/?$`)); await expect(title(page)).toHaveValue("Synthetic title");
  expect(audit.writes.filter(write => write.path === "/media/assets")).toHaveLength(1);
  expect(audit.writes.filter(write => write.path.endsWith("/manual-social/posts"))).toHaveLength(0);
  expect(audit.discarded).toEqual([]);
});

test("changed content after a failed request uses a new key while retaining the selected asset", async ({ page }, info) => {
  const audit = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  audit.postFailures = 1; await page.goto(feedRoute()); await fill(page);
  await composer(page).locator('input[type="file"]').setInputFiles(synthetic("webp", "image/webp"));
  await expect(composer(page).getByRole("button", { name: "사진 제거" })).toBeVisible();
  await publish(page).click(); await expect(publish(page)).toBeEnabled();
  await body(page).fill("Changed body"); await publish(page).click(); await expect(body(page)).toHaveValue("");
  const writes = audit.writes.filter(write => write.path.endsWith("/manual-social/posts"));
  expect(writes).toHaveLength(2); expect(writes[1].key).not.toBe(writes[0].key);
  expect(writes[1].body).toEqual({ title: "Synthetic title", body: "Changed body", attachment_asset_id: "draft-1" });
  expect(audit.posts).toHaveLength(1); expect(audit.discarded).toEqual([]);
});

test("global and World header/composer anchors match and global controls remain available", async ({ page }, info) => {
  const audit = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  audit.globalName = OWNER_NAME;
  audit.posts.push(uiDManualPost({ id: "anchor-post", worldId: FEED_WORLD, title: "Common title", body: "Common long body. ".repeat(100), likeCount: 3, replyCount: 2 }));
  const measurements = [];
  const measure = () => page.evaluate(() => {
    const rect = (element: Element | null) => {
      if (!element) return null;
      const r = element.getBoundingClientRect(), s = getComputedStyle(element);
      return { x: r.x, y: r.y, width: r.width, height: r.height, fontSize: s.fontSize, lineHeight: s.lineHeight, borderRadius: s.borderRadius };
    };
    const field = document.querySelector("textarea"), form = field?.closest("form");
    return { header: rect(document.querySelector("[data-feed-header]")), title: rect(document.querySelector("[data-feed-header] h1")),
      logo: rect(document.querySelector("[data-feed-header-center]")), right: rect(document.querySelector("[data-feed-header-right]")),
      avatar: rect(form?.querySelector('[data-ui-primitive="avatar"]') ?? null), field: rect(field),
      postAvatar: rect(document.querySelector('[data-social-post-row="anchor-post"] [data-ui-primitive="avatar"]')),
      postBody: rect(document.querySelector('[data-social-post-row="anchor-post"] p')) };
  });
  for (const width of [390, 480, 768, 960, 1440]) {
    await page.setViewportSize({ width, height: 1000 }); await page.goto("/posts");
    await expect(page.locator("textarea")).toBeVisible();
    await expect(page.getByRole("button", { name: "리포스트", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "전체", exact: true }).click();
    await expect(page.locator('[data-social-post-row="anchor-post"]')).toBeVisible();
    if (width < 768) {
      const trigger = page.locator("[data-feed-header-right] button"); await expect(trigger).toBeVisible();
      await trigger.click(); await expect(page.getByRole("dialog")).toBeVisible();
      await page.getByRole("dialog").getByRole("button", { name: "닫기", exact: true }).last().click();
    } else await expect(page.getByRole("button", { name: "새로고침", exact: true })).toBeVisible();
    const global = await measure();
    await page.goto(feedRoute()); await expect(composer(page)).toBeVisible(); const world = await measure();
    for (const [before, after] of [[global.title, world.title], [global.avatar, world.avatar], [global.field, world.field], [global.postAvatar, world.postAvatar], [global.postBody, world.postBody]]) {
      expect(Math.abs(before!.x - after!.x)).toBeLessThanOrEqual(1);
      expect(before!.width).toBe(after!.width);
    }
    expect(global.title!.fontSize).toBe(world.title!.fontSize);
    expect(global.field!.borderRadius).toBe(world.field!.borderRadius);
    expect(global.field!.fontSize).toBe(world.field!.fontSize);
    expect(global.field!.lineHeight).toBe(world.field!.lineHeight);
    expect(global.postBody!.height).toBe(world.postBody!.height);
    expect(global.postBody!.fontSize).toBe(world.postBody!.fontSize);
    if (width < 768) {
      expect(global.logo!.x).toBe(world.logo!.x); expect(global.right!.x + global.right!.width).toBe(world.right!.x + world.right!.width);
    } else await expect(page.locator("[data-feed-header-right] a")).toBeVisible();
    measurements.push({ width, global, world });
  }
  writeFileSync(info.outputPath("anchor-geometry.json"), JSON.stringify(measurements, null, 2));
  expect(audit.providerCalls).toEqual([]); expect(audit.writes).toEqual([]);
});

test("detail and other World sections keep their own shell and detail navigation", async ({ page }, info) => {
  const audit = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await page.goto(`/worlds/${FEED_WORLD}/posts/original`);
  await expect(page.getByRole("heading", { name: "게시글과 답글", exact: true })).toBeVisible();
  await expect(page.locator("[data-feed-header]")).toHaveCount(0); await expect(composer(page)).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Feed", exact: true })).toBeVisible();
  await page.goto(`/worlds/${FEED_WORLD}`); await expect(page.getByRole("heading", { name: uiWorldName(), level: 1, exact: true })).toBeVisible();
  await expect(page.locator("[data-feed-header]")).toHaveCount(0); expect(audit.providerCalls).toEqual([]);
});

test("existing post row retains title, body, expansion and profile/detail capabilities", async ({ page }, info) => {
  const audit = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  audit.posts.push(uiDManualPost({ id: "existing", worldId: FEED_WORLD, title: "Existing title", body: "Existing body. ".repeat(120), likeCount: 3, replyCount: 2 }));
  await page.goto(feedRoute()); const row = page.locator('[data-social-post-row="existing"]');
  await expect(row).toContainText("Existing title"); await expect(row.getByRole("button", { name: "더보기", exact: true })).toBeVisible();
  await row.getByRole("button", { name: "더보기", exact: true }).click(); await expect(row).toContainText("Existing body.");
  await expect(row.getByRole("link").first()).toHaveAttribute("href", /world-feed-alpha\/characters\/wc-ui-d-autonomous/);
  await row.press("Enter"); await expect(page).toHaveURL(/\/posts\/existing$/); expect(audit.writes).toEqual([]);
});

for (const language of ["ko", "en"] as const) test(`responsive positions, long owner, focus and zoom (${language})`, async ({ page }, info) => {
  const audit = await installWorldFeedFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
  audit.displayName = "LongSyntheticWorldOwnerName".repeat(4); await page.goto(feedRoute()); await expect(composer(page)).toBeVisible();
  await fill(page, "Ready title", "Ready body");
  await expect(publish(page)).toHaveCSS("background-color", "rgb(255, 107, 107)");
  await expect(publish(page)).toHaveCSS("color", "rgb(255, 255, 255)");
  for (const [width, height] of [[360,800],[390,844],[436,880],[480,850],[768,1024],[960,900],[1440,1000]]) {
    await page.setViewportSize({ width, height });
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
    const frame = page.locator('[data-product-shell="device"]');
    expect((await frame.boundingBox())!.width).toBe(Math.min(width, 960));
    for (const action of [photo(page), publish(page)]) { const rect = await action.boundingBox(); expect(rect!.width).toBe(48); expect(rect!.height).toBe(48); }
    const profile = page.locator("[data-feed-header]").getByRole("link", { name: language === "ko" ? "내 프로필" : "My Profile", exact: true });
    await expect(profile).toBeVisible();
    await page.screenshot({ path: info.outputPath(`world-${language}-${width}x${height}.png`) });
  }
  await page.setViewportSize({ width: 480, height: 850 }); await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
  await photo(page).focus(); await expect(photo(page)).toBeFocused();
  expect(await photo(page).evaluate(el => getComputedStyle(el).outlineStyle)).not.toBe("none");
  await page.screenshot({ path: info.outputPath(`world-${language}-zoom-focus.png`) });
});
