import { expect, test } from "@playwright/test";
import { FEED_WORLD } from "./world-feed-fixture";
import { installWorldCharacterManagementFixture, worldCharacterRoute, WORLD_AGENT } from "./world-character-management-fixture";
import { continuityAgentDetail } from "./continuity-fixture";

for (const language of ["ko", "en"] as const) {
  for (const width of [390, 960]) {
    test(`Status cards reuse identity and bounded activity scrolling (${language}, ${width})`, async ({ page }, info) => {
      await page.setViewportSize({ width, height: 1000 });
      const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
      const actor = state.management.worlds.get(FEED_WORLD)!.find(item => item.profile.world_character_id === WORLD_AGENT)!;
      actor.next_activity_at = "2026-10-07T09:05:00Z";
      state.management.statusActivity = Array.from({ length: 20 }, (_, index) => ({
        id: `activity-${index}`, action: index % 3 === 1 ? "reply" : index % 3 === 2 ? "like" : "post",
        status: index === 2 ? "failed" : index === 3 ? "blocked" : "completed",
        occurred_at: `2026-10-07T08:${String(29 - index).padStart(2, "0")}:00Z`,
        post_id: index === 2 || index === 3 ? null : `source-${index}`,
        title: `Original activity ${index + 1}`,
      }));
      await page.goto(`${worldCharacterRoute()}?view=status`);
      const surface = page.locator("[data-world-character-management]");
      const panel = surface.getByRole("tabpanel");
      const identity = panel.getByRole("region", { name: "Synthetic Responder", exact: true });
      await expect(identity.getByRole("heading", { name: "Synthetic Responder", exact: true })).toBeVisible();
      await expect(identity.getByRole("img")).toHaveCount(1);
      await expect(identity).toContainText("@synthetic_responder");
      await expect(identity).toContainText(actor.profile.intro);
      await expect(identity.locator("time").first()).toHaveAttribute("dateTime", "2026-10-07T08:29:00Z");
      await expect(identity.locator("time").last()).toHaveAttribute("dateTime", actor.next_activity_at);
      await expect(identity).toContainText(language === "ko" ? "활동 시간 대기" : "Waiting for activity hours");
      await expect(panel).not.toContainText(/이 World에서만 적용되는 활동 상태예요|Activity status applies only in this World/);
      await expect(panel).not.toContainText(/리포스트|언팔로우|repost|unfollow/i);
      const cards = panel.locator(":scope > div > section");
      await expect(cards).toHaveCount(4);
      const panelBox = (await panel.boundingBox())!;
      for (const card of await cards.all()) {
        const box = (await card.boundingBox())!;
        expect(Math.round(box.x - panelBox.x)).toBe(width >= 768 ? 36 : 16);
        expect(Math.round(panelBox.x + panelBox.width - box.x - box.width)).toBe(width >= 768 ? 36 : 16);
      }
      const scroll = panel.getByRole("region", { name: language === "ko" ? "최근 활동" : "Recent activity", exact: true });
      await expect(scroll.locator("article")).toHaveCount(10);
      await expect(scroll).toContainText(language === "ko" ? "실패" : "Failed");
      await expect(scroll).toContainText(language === "ko" ? "실행 보류" : "Execution paused");
      const dimensions = await scroll.evaluate(node => ({ height: node.clientHeight, content: node.scrollHeight }));
      expect(dimensions.height).toBeLessThanOrEqual(568);
      expect(dimensions.content).toBeGreaterThan(dimensions.height);
      await expect(scroll.locator("[data-activity-log-timezone]")).toHaveAttribute("data-activity-log-timezone", "Asia/Seoul");
      await expect(scroll.getByRole("link", { name: language === "ko" ? "답글을 남긴 글 보기" : "View replied post", exact: true }).first()).toHaveAttribute("href", `/worlds/${FEED_WORLD}/posts/source-1${info.project.name === "static-export" ? "/" : ""}`);
      for (const link of await scroll.getByRole("link").all()) expect((await link.boundingBox())!.height).toBeGreaterThanOrEqual(44);

      await scroll.scrollIntoViewIfNeeded();
      const owner = page.locator('[data-device-scroll-owner="true"]');
      const outerTop = await owner.evaluate(node => node.scrollTop);
      const scrollBox = (await scroll.boundingBox())!;
      await page.mouse.move(scrollBox.x + scrollBox.width / 2, Math.max(250, scrollBox.y) + 80);
      await page.mouse.wheel(0, 350);
      await expect.poll(() => scroll.evaluate(node => node.scrollTop)).toBeGreaterThan(0);
      expect(await owner.evaluate(node => node.scrollTop)).toBe(outerTop);
      for (let index = 0; index < 3; index++) {
        await scroll.evaluate(node => node.scrollTop = node.scrollHeight);
        await expect(scroll.locator("article")).toHaveCount(Math.min(20, 15 + index * 5));
      }
      await expect(scroll).toContainText("Original activity 20");
      const savedTop = await scroll.evaluate(node => node.scrollTop);
      await surface.getByRole("tab", { name: language === "ko" ? "설정" : "Settings", exact: true }).click();
      await surface.getByRole("tab", { name: language === "ko" ? "상태" : "Status", exact: true }).click();
      expect(await scroll.evaluate(node => node.scrollTop)).toBe(savedTop);
      await expect(scroll.locator("article")).toHaveCount(20);
      const labels = await panel.locator("article h3").allTextContents();
      expect(labels[0]).toBe(language === "ko" ? "캐릭터 설명" : "Character description");
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
      expect(state.management.writes).toEqual([]);
      expect(state.management.providerCalls).toEqual([]);
      await scroll.evaluate(node => node.scrollTop = 0);
      await owner.evaluate(node => node.scrollTop = 0);
      await page.screenshot({ path: info.outputPath(`world-status-${language}-${width}.png`), fullPage: true });
    });
  }

  test(`Status cards preserve OFF, missing activity, retry and World access (${language})`, async ({ page }, info) => {
    const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    state.management.statusActivity = [];
    await page.goto(`${worldCharacterRoute("off-agent")}?view=status`);
    const panel = page.getByRole("tabpanel");
    await expect(panel.getByRole("region", { name: "Synthetic off-agent", exact: true })).toContainText(language === "ko" ? "자율활동 꺼짐" : "Autonomous activity is off");
    await expect(panel.getByRole("region", { name: language === "ko" ? "최근 활동" : "Recent activity", exact: true })).toContainText(language === "ko" ? "최근 활동이 없습니다." : "No recent activity.");
    await expect(panel.locator("time")).toHaveCount(0);
    state.management.statusFailure = 403;
    await page.reload();
    await expect(panel.getByRole("heading", { name: "Synthetic off-agent", exact: true })).toHaveCount(0);
    await expect(panel.getByRole("button", { name: language === "ko" ? "다시 시도" : "Retry", exact: true })).toBeVisible();
    state.management.statusFailure = 0;
    await panel.getByRole("button", { name: language === "ko" ? "다시 시도" : "Retry", exact: true }).click();
    await expect(panel.getByRole("heading", { name: "Synthetic off-agent", exact: true })).toBeVisible();
    expect(state.management.writes).toEqual([]);
    expect(state.management.providerCalls).toEqual([]);
  });
}

test("Status cards keep the original Device identity and activity links", async ({ page }, info) => {
  await page.setViewportSize({ width: 960, height: 1000 });
  const state = await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  const agent = { ...continuityAgentDetail("synthetic-device"), recent_activity: Array.from({ length: 20 }, (_, index) => ({
    id: index + 1, action_type: index % 2 ? "replied" : "post_created", created_at: "2026-10-07T08:29:00Z",
    target_post_id: `device-post-${index}`, result: index % 2 ? "Created reply" : "Created post",
  })) };
  await page.route("**/api/backend/agents/synthetic-device", route => route.fulfill({ json: agent }));
  await page.route("http://127.0.0.1:8080/api/v1/agents/synthetic-device", route => route.fulfill({ json: agent }));
  await page.goto("/agents/synthetic-device");
  await page.getByRole("tab", { name: "상태", exact: true }).click();
  const identity = page.getByRole("region", { name: "Profile Scroll Parrot", exact: true });
  await expect(identity.getByRole("heading", { name: "Profile Scroll Parrot", exact: true })).toBeVisible();
  await expect(identity).toContainText("@profile_scroll");
  await expect(identity).toContainText("Device owner pagination probe");
  const scroll = page.getByRole("region", { name: "최근 활동", exact: true });
  await expect(scroll.locator("article")).toHaveCount(10);
  await expect(scroll.getByRole("link", { name: "답글을 남긴 글 보기", exact: true }).first()).toHaveAttribute("href", `/posts/device-post-1${info.project.name === "static-export" ? "/" : ""}`);
  expect(await scroll.evaluate(node => node.scrollHeight > node.clientHeight)).toBe(true);
  expect(state.management.writes).toEqual([]);
  expect(state.management.providerCalls).toEqual([]);
});
