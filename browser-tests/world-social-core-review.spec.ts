import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { installSocialChatFixture, chatRoute } from "./world-social-chat-fixture";
import { FEED_WORLD } from "./world-feed-fixture";

for (const language of ["ko", "en"] as const) {
  test(`translated photo Chat settles committed and survives reload (${language})`, async ({page}, info) => {
    const state = await installSocialChatFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    await page.goto(chatRoute());
    const form = page.locator('[data-world-chat-surface="thread"] form');
    await form.locator("textarea").fill("Original user text");
    const chooser = page.waitForEvent("filechooser");
    await form.getByRole("button", {name: language === "ko" ? "사진 첨부" : "Attach photo", exact: true}).click();
    await (await chooser).setFiles({name:"photo.webp", mimeType:"image/webp", buffer:readFileSync("../backend/tests/image_integration/fixtures/pixels.webp")});
    await expect(form.locator("img")).toBeVisible();
    const opposite = language === "ko" ? "en" : "ko";
    state.base.language = opposite;
    await page.evaluate(() => window.dispatchEvent(new Event("angmoo:auth-changed")));
    await form.getByRole("button", {name: opposite === "ko" ? "메시지 보내기" : "Send message", exact:true}).click();
    await expect.poll(() => state.reads.some(path => path.endsWith("/requests/synthetic-request"))).toBe(true);
    await expect(page.getByText("Synthetic complete answer", {exact:true})).toBeVisible();
    await expect(page.locator('[data-world-chat-surface="thread"] [role="alert"]')).toHaveCount(0);
    await page.reload();
    await expect(page.getByText("Synthetic complete answer", {exact:true})).toBeVisible();
    const writes = state.writes.filter(write => write.path.endsWith("/messages"));
    expect(writes).toHaveLength(1);
    expect(writes[0].data.content).toBe("Original user text");
    expect(writes[0].data.attachment_asset_id).toBe("draft-1");
    expect(state.base.providerCalls).toEqual([]);
  });
}

test("profile query change keeps the document and late reaction receipt", async ({page}, info) => {
  const state = await installSocialChatFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  state.posts[0].author_world_character_id = "synthetic-responder";
  state.delay = 1500;
  await page.goto(`/worlds/${FEED_WORLD}/characters/synthetic-responder`);
  const row = page.locator('[data-social-post-row="synthetic-root"]');
  await expect(row).toBeVisible();
  await page.evaluate(() => Object.assign(window, {coreReviewDocument:"retained"}));
  await row.getByRole("button", {name:/좋아요/}).click();
  await page.getByRole("tab", {name:"좋아요", exact:true}).click();
  await expect(page).toHaveURL(/tab=likes/);
  expect(await page.evaluate(() => (window as unknown as {coreReviewDocument?:string}).coreReviewDocument)).toBe("retained");
  await expect(row).toBeVisible();
  await expect(row.getByRole("button", {name:/좋아요/})).toHaveAttribute("aria-pressed", "true");
  await expect(row.getByRole("button", {name:/좋아요/})).toBeEnabled();
  expect(state.writes.filter(write => write.path.endsWith("/like"))).toHaveLength(1);
  await page.reload();
  await expect(row.getByRole("button", {name:/좋아요/})).toHaveAttribute("aria-pressed", "true");
  expect(state.base.providerCalls).toEqual([]);
});
