import { expect, test } from "@playwright/test";
import { installWorldCharacterManagementFixture, syntheticWorldCharacter, WORLD_AGENT } from "./world-character-management-fixture";
import { FEED_WORLD } from "./world-feed-fixture";
import { memoryBatchFixture } from "./memory-batch-fixture";

for (const language of ["ko", "en"] as const) test(`failed review offers retry and close without re-execution (${language})`, async ({ page }, info) => {
  await installWorldCharacterManagementFixture(page, false, String(info.project.use.baseURL), language);
  const scope = { world_id: FEED_WORLD, subject_world_character_id: WORLD_AGENT };
  const batch = memoryBatchFixture(FEED_WORLD, WORLD_AGENT, () => true);
  const progress = { request_id: "failed-request", effective_request_id: "failed-request", kind: "manual",
    accepted_at: "2026-10-29T03:00:00Z", state: "no_work", saved_count: 4, remaining_count: 0,
    job_count: 0, completed_job_count: 0, last_code: null, workflow_version: 2, followup: "relationships",
    flow_state: "relationship_retry_needed", revision: 0, actions: ["regenerate_failed", "close_without_retry"], requires_new_ai_call: true,
    relationship: {state: "partial_failed", request_id: "failed-request", target_count: 2, memory_count: 4,
      completed_count: 1, kept_count: 1, changed_count: 0, failed_count: 1, closed_count: 0, last_code: null, completed_at: null} };
  const mutations: unknown[] = [];
  await page.route("**/api/backend/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith(`/worlds/${FEED_WORLD}/world-characters`)) return route.fulfill({json:{
      schema_version:"world-character-profile-list-v1",world_id:FEED_WORLD,items:[syntheticWorldCharacter(WORLD_AGENT).profile]}});
    if (!path.includes(`/world-characters/${WORLD_AGENT}/`)) return route.fallback();
    if (path.endsWith("/memory/batch-progress")) return route.fulfill({json:{scope,capability:{relationships:true,reason:null},progress}});
    if (path.endsWith("/memory/batch-run/failed-request/cancel")) {
      const body = route.request().postDataJSON(); mutations.push(body);
      expect(body.mode).toBe("close_without_retry"); expect(body.expected_revision).toBe(0);
      Object.assign(progress, {flow_state: "closed", revision: 1, actions: [], requires_new_ai_call: false});
      Object.assign(progress.relationship, {state:"closed",closed_count:1});
      return route.fulfill({json:{scope,capability:{relationships:true,reason:null},progress}});
    }
    if (await batch(route)) return;
    const capabilities = {read:"available", mutate:"available"};
    if (path.endsWith("/memory/settings")) return route.fulfill({json:{
      schema_version:"memory-setting-read.v1",scope,configured:true,enabled:true,retention_days:180,provider_mode:"optional-configured",version:1,capabilities}});
    if (path.endsWith("/memories")) return route.fulfill({json:{
      schema_version:"memory-item-list.v1",scope,memory_enabled:true,items:[],next_cursor:null,capabilities}});
    return route.fallback();
  });
  await page.setViewportSize({width:390,height:900});
  await page.goto(`/memory?world=${FEED_WORLD}&subject=${WORLD_AGENT}`);
  const close = page.getByRole("button",{name:language === "ko" ? "재시도 없이 종료" : "Close without retrying",exact:true});
  const retry = page.getByRole("button",{name:language === "ko" ? "실패한 부분 다시 판단" : "Review failed items again",exact:true});
  await expect(close).toBeVisible(); await expect(retry).toBeVisible();
  expect((await close.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await close.click();
  await expect(close).toHaveCount(0); await expect(retry).toHaveCount(0);
  await expect(page.getByText(language === "ko" ? "완료된 결과와 실패 이력을 보존하고 종료했습니다." : "Closed without retrying. Completed results and failure history were kept.",{exact:true})).toBeVisible();
  expect(mutations).toHaveLength(1);
  await page.reload();
  await expect(close).toHaveCount(0); expect(mutations).toHaveLength(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
});
