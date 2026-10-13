import { test, expect, type Page } from "@playwright/test";
import { installIntegrationFixture } from "./home-activity-memory-fixture";
import { FEED_WORLD } from "./world-feed-fixture";
import { WORLD_AGENT } from "./world-character-management-fixture";

async function register(page: Page, language: "ko" | "en") {
  const next = language === "ko" ? "저장하고 다음" : "Save and continue";
  await page.goto(`/agents/new?worldId=${FEED_WORLD}`);
  await page.getByRole("button", { name: next, exact: true }).click();
  await page.getByRole("textbox", { name: language === "ko" ? "이름" : "Name", exact: true }).fill("Registered review character");
  await page.getByRole("button", { name: next, exact: true }).click();
  await page.getByRole("textbox", { name: language === "ko" ? "캐릭터 설명" : "Character description", exact: true }).fill("A careful character who keeps a promise.");
  await page.getByRole("button", { name: next, exact: true }).click();
  await page.getByRole("button", { name: next, exact: true }).click();
  await page.getByRole("button", { name: language === "ko" ? "등록" : "Register", exact: true }).click();
}

for (const failure of ["missing", "world", "character"] as const) {
  test(`review registration: ${failure} scope preserves completion, explicit retry and skip`, async ({ page }, info) => {
    const language = failure === "world" ? "en" : "ko";
    const state = await installIntegrationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
    state.registrationScopeFailure = failure;
    await register(page, language);
    const retry = page.getByRole("button", { name: language === "ko" ? "등록 결과 확인" : "Review registration", exact: true });
    const skip = page.getByRole("button", { name: language === "ko" ? "건너뛰기" : "Skip", exact: true });
    const card = page.getByRole("region", { name: language === "ko" ? "활동 설정" : "Activity settings", exact: true });
    await expect(skip).toBeVisible();
    await expect(card).toHaveCount(0);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(language === "ko" ? "등록 완료" : "Registration complete");
    await expect(page.locator('section[aria-labelledby="created-heading"]').getByRole("alert")).toBeVisible();
    const policyWrites = () => state.writes.filter(row => /credentials|activity-settings|activate|image-policy/.test(row.path));
    const draftEdits = state.writes.filter(row => row.path.endsWith("/integration-draft")).length;
    await retry.click(); await expect.poll(() => state.completeCalls).toBe(2);
    await expect(skip).toBeVisible(); await expect(card).toHaveCount(0);
    state.registrationScopeFailure = "none";
    await retry.click(); await expect(card).toContainText(language === "ko" ? "자율활동 OFF" : "Autonomous activity OFF");
    expect(state.registrations).toBe(1);
    expect(state.writes.filter(row => row.path.endsWith("/integration-draft"))).toHaveLength(draftEdits);
    state.registrationScopeFailure = failure;
    await page.reload(); await expect(skip).toBeVisible(); await expect(card).toHaveCount(0);
    await skip.click(); await expect(page).toHaveURL(new RegExp(`/worlds/${FEED_WORLD}/characters/?$`));
    expect(await page.evaluate(world => sessionStorage.getItem(`angmoo.creation.v2:${world}`), FEED_WORLD)).toBeNull();
    expect(state.registrations).toBe(1); expect(policyWrites()).toEqual([]);
    expect(state.ui.management.providerCalls).toEqual([]); expect(state.unexpected).toEqual([]);
  });
}

test("review owner: denied receipt restore cannot retain another owner's completed registration", async ({ page }, info) => {
  const state = await installIntegrationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
  await register(page, "ko");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Registered review character");
  state.ui.management.authOwner = "another-local-owner"; state.draftReadFailure = 403;
  await page.evaluate(() => window.dispatchEvent(new Event("angmoo:auth-changed")));
  await expect(page.getByRole("heading", { level: 1 })).not.toContainText("Registered review character");
  await expect(page.getByRole("region", { name: "활동 설정", exact: true })).toHaveCount(0);
  await expect(page.locator('section[aria-labelledby="creation-heading"]').getByRole("alert")).toBeVisible();
  expect(state.registrations).toBe(1); expect(state.completeCalls).toBe(1);
  expect(state.ui.management.providerCalls).toEqual([]); expect(state.unexpected).toEqual([]);
});

for (const change of ["runtime", "owner"] as const) {
  test(`review scope: ${change} change clears image policy draft and unsaved Partner key`, async ({ page }, info) => {
    const state = await installIntegrationFixture(page, info.project.name === "static-export", String(info.project.use.baseURL));
    state.ui.management.credentials.set(`${FEED_WORLD}:${WORLD_AGENT}:image`, {
      provider: "comfyui", model: "workflow", thinking_level: null, has_key: false, has_partner_key: true,
      fingerprint: null, revision: 1, key_revision: 1, configuration_revision: 1,
    });
    await register(page, "ko");
    const card = page.getByRole("region", { name: "SNS 게시글 이미지 생성", exact: true });
    const appearance = card.getByLabel("외형 (선택)", { exact: true });
    const partner = card.getByLabel("Comfy 계정 API 키", { exact: true });
    await partner.fill("synthetic-unsaved-partner-key");
    await appearance.fill("Unsaved previous scope appearance");
    if (change === "owner") state.ui.management.authOwner = "new-local-owner";
    await page.evaluate(kind => {
      window.dispatchEvent(new Event(kind === "runtime" ? "angmoo:desktop-runtime-config-changed" : "angmoo:auth-changed"));
    }, change);
    await expect(appearance).toHaveValue(""); await expect(partner).toHaveValue("");
    expect(state.registrations).toBe(1);
    expect(state.writes.filter(row => /credentials|activity-settings|activate|image-policy/.test(row.path))).toEqual([]);
    expect(state.ui.management.providerCalls).toEqual([]); expect(state.unexpected).toEqual([]);
  });
}
