import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { installWorldCharacterManagementFixture, syntheticWorldCharacter, WORLD_AGENT } from "./world-character-management-fixture";
import { FEED_WORLD } from "./world-feed-fixture";
import { memoryBatchFixture } from "./memory-batch-fixture";

const SECOND = "01a0f751-3bfb-7388-a914-400990cd56a0";
const copy = {
  ko: { global: "저장하지 못한 경험 다시 확인", recheck: "다시 확인", discard: "이 경험 저장 포기",
    list: "저장하지 못한 경험 목록", more: "저장하지 못한 경험 더 보기", cancel: "취소", retry: "같은 요청 다시 확인",
    result: "다시 확인한 결과: 저장 1개 · 확인 실패 1개 · 건너뜀 0개", none: "저장하지 못한 경험이 없어요." },
  en: { global: "Recheck unsaved experiences", recheck: "Recheck", discard: "Discard this unsaved experience",
    list: "Unsaved experience list", more: "Load more unsaved experiences", cancel: "Cancel", retry: "Check the same request again",
    result: "Recheck result: 1 saved, 1 could not be verified, 0 skipped", none: "There are no unsaved experiences." },
};

async function fixture(page: Page, info: TestInfo, language: "ko" | "en", off = false) {
  await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
  const scope = { world_id: FEED_WORLD, subject_world_character_id: WORLD_AGENT };
  const state = { scope, version: 1, memory_enabled: !off, daily_enabled: false, local_time: "22:30", timezone: "Asia/Seoul",
    shutdown_apply_enabled: true, next_due_at: null, last_applied_at: null, pending_count: 1, blocked_count: 21, applied_count: 0,
    status: "idle", result: null as string | null, operation: null as string | null, run_id: null as string | null, run_state: null as string | null,
    rejected_count: 0, skipped_count: 0, scope_busy: false, can_recheck: !off };
  const rows = Array.from({ length: 21 }, (_, index) => ({ receipt_sequence: index + 1, state_version: 1,
    occurred_at: "2026-10-08T08:00:00Z", description: index === 1 ? null : `SAFE_EXPERIENCE_${index + 1}`,
    reason: index === 1 ? "proof_unavailable" : "source_changed", can_recheck: !off, can_discard: true }));
  const writes: { path: string; body: Record<string, unknown> }[] = [];
  const controls = { abortDiscard: false, wrongKey: false, barrier: null as Promise<void> | null, resolvedKey: null as string | null,
    listBarrier: null as Promise<void> | null, listWaiting: false, finishRecheck: false, workerError: false };
  const batch = memoryBatchFixture(FEED_WORLD, WORLD_AGENT, () => state.memory_enabled);
  const secondBatch = memoryBatchFixture(FEED_WORLD, SECOND, () => true);
  await page.route(info.project.name === "static-export" ? "http://127.0.0.1:8080/api/v1/**" : "**/api/backend/**", async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    if (path.endsWith(`/worlds/${FEED_WORLD}/world-characters`)) return route.fulfill({ json: {
      schema_version: "world-character-profile-list-v1", world_id: FEED_WORLD,
      items: [syntheticWorldCharacter(WORLD_AGENT).profile, syntheticWorldCharacter(SECOND).profile] } });
    const second = path.includes(`/world-characters/${SECOND}/`), activeScope = second ? { ...scope, subject_world_character_id: SECOND } : scope;
    if (!second && !path.includes(`/world-characters/${WORLD_AGENT}/`)) return route.fallback();
    if (request.method() !== "GET") writes.push({ path, body: request.postDataJSON() });
    if (path.endsWith("/memory/unsaved-experiences")) {
      if (!second && controls.listBarrier) { controls.listWaiting = true; await controls.listBarrier; }
      const cursor = url.searchParams.get("cursor"), items = second ? [] : cursor ? rows.slice(20) : rows.slice(0, 20);
      return route.fulfill({ json: { scope: activeScope, items, next_cursor: !second && !cursor && rows.length > 20 ? "bounded-next-page" : null,
        blocked_count: second ? 0 : state.blocked_count, scope_busy: state.scope_busy, can_recheck: !off } });
    }
    if (path.endsWith("/memory/processing-settings")) {
      if (controls.finishRecheck) Object.assign(state, { status: "partial_error", run_state: controls.workerError ? "error" : "completed", result: "accepted", blocked_count: 1,
        applied_count: 1, rejected_count: 1, skipped_count: 0, scope_busy: false, can_recheck: !off });
      return route.fulfill({ json: { ...state, scope: activeScope, ...(second ? { blocked_count: 0, pending_count: 77, can_recheck: true } : {}),
        resolved_request_key: url.searchParams.get("request_key") === controls.resolvedKey ? controls.resolvedKey : null } });
    }
    if (path.endsWith("/recheck")) {
      if (controls.barrier) await controls.barrier;
      controls.resolvedKey = String(request.postDataJSON().idempotency_key);
      Object.assign(state, { operation: "blocked_recheck", run_id: "synthetic-recheck", run_state: "pending", status: "accepted", result: "accepted", scope_busy: true });
      return route.fulfill({ status: 202, json: { ...state, resolved_request_key: controls.wrongKey ? "wrong-request-key" : controls.resolvedKey } });
    }
    if (path.endsWith("/discard")) {
      const sequence = Number(path.split("/").at(-2)), body = request.postDataJSON();
      const index = rows.findIndex(row => row.receipt_sequence === sequence);
      if (index >= 0) { rows.splice(index, 1); state.blocked_count -= 1; }
      if (controls.abortDiscard) { controls.abortDiscard = false; return route.abort("failed"); }
      return route.fulfill({ json: { scope, receipt_sequence: sequence, state: "discarded", state_version: 2,
        discarded_at: "2026-10-08T09:00:00Z", operation: "discard", result: index < 0 ? "already_discarded" : "discarded",
        resolved_request_key: body.idempotency_key, pending_count: state.pending_count, blocked_count: state.blocked_count } });
    }
    if (await (second ? secondBatch : batch)(route)) return;
    const capabilities = { read: "available", mutate: "available" };
    if (path.endsWith("/memory/settings")) return route.fulfill({ json: {
      schema_version: "memory-setting-read.v1", scope: activeScope, configured: true, enabled: second || state.memory_enabled,
      retention_days: 180, provider_mode: "optional-configured", version: 1, capabilities } });
    if (path.endsWith("/memories")) return route.fulfill({ json: {
      schema_version: "memory-item-list.v1", scope: activeScope, memory_enabled: state.memory_enabled, items: [], next_cursor: null, capabilities } });
    return route.fulfill({ status: 404, json: { detail: "unexpected_recovery_fixture_request" } });
  });
  await page.goto(`/memory?world=${FEED_WORLD}&subject=${WORLD_AGENT}`);
  const panel = page.locator("[data-memory-unsaved]");
  await expect(panel.locator("[data-unsaved-experience]")).toHaveCount(20);
  return { panel, state, rows, writes, controls };
}

for (const language of ["ko", "en"] as const) {
  const words = copy[language];
  test(`bounded list, three actions, keyboard dialog and mobile layout (${language})`, async ({ page }, info) => {
    const { panel, writes } = await fixture(page, info, language);
    await expect(panel.getByRole("button", { name: words.global, exact: true })).toBeEnabled();
    const list = panel.getByRole("region", { name: words.list });
    expect(await list.evaluate(element => element.scrollHeight > element.clientHeight && element.clientHeight <= 440)).toBe(true);
    await list.focus(); await expect(list).toBeFocused();
    await panel.getByRole("button", { name: words.more }).click();
    await expect(panel.locator("[data-unsaved-experience]")).toHaveCount(21);
    await expect(panel.getByRole("button", { name: words.more })).toHaveCount(0);
    const first = panel.locator('[data-unsaved-experience="1"]');
    await first.getByRole("button", { name: words.discard, exact: true }).click();
    const dialog = page.getByRole("dialog", { name: words.discard });
    await expect(dialog.getByRole("button", { name: words.cancel, exact: true })).toBeFocused();
    await page.keyboard.press("Tab"); await expect(dialog.getByRole("button", { name: words.discard, exact: true })).toBeFocused();
    await page.keyboard.press("Escape"); await expect(dialog).toHaveCount(0);
    await expect(first.getByRole("button", { name: words.discard, exact: true })).toBeFocused();
    expect(writes).toHaveLength(0);
    for (const width of [360, 1100]) {
      await page.setViewportSize({ width, height: 980 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
      for (const name of [words.recheck, words.discard]) {
        const size = await first.getByRole("button", { name, exact: true }).boundingBox();
        expect(size!.height).toBeGreaterThanOrEqual(44);
      }
      await panel.screenshot({ path: `../artifacts/situation-recovery-validation/${info.project.name}-${language}-${width}.png` });
    }
  });

  test(`OFF permits discard; ambiguous result retries the identical request (${language})`, async ({ page }, info) => {
    const { panel, writes, controls } = await fixture(page, info, language, true);
    await expect(panel.getByRole("button", { name: words.global, exact: true })).toBeDisabled();
    const first = panel.locator('[data-unsaved-experience="1"]');
    await expect(first.getByRole("button", { name: words.recheck, exact: true })).toBeDisabled();
    await expect(first.getByRole("button", { name: words.discard, exact: true })).toBeEnabled();
    controls.abortDiscard = true;
    await first.getByRole("button", { name: words.discard, exact: true }).click();
    await page.getByRole("dialog").getByRole("button", { name: words.discard, exact: true }).click();
    await expect(panel.getByRole("alert")).toBeVisible();
    await panel.getByRole("button", { name: words.retry, exact: true }).click();
    await expect(panel.getByRole("alert")).toHaveCount(0);
    await expect(panel.locator('[data-unsaved-experience="1"]')).toHaveCount(0);
    expect(writes).toHaveLength(2); expect(writes[1]).toEqual(writes[0]);
    await expect(panel.getByRole("heading")).toBeFocused();
    await expect(panel.getByRole("heading")).toHaveText(language === "ko" ? "저장하지 못한 경험 20개" : "20 unsaved experiences");
  });

  for (const individual of [false, true]) test(`recheck ${individual ? "individual target" : "whole frozen scope"} reports partial result and locks mutations (${language})`, async ({ page }, info) => {
    const { panel, controls, writes } = await fixture(page, info, language);
    let finish!: () => void; controls.barrier = new Promise(resolve => { finish = resolve; });
    const button = individual ? panel.locator('[data-unsaved-experience="1"]').getByRole("button", { name: words.recheck, exact: true })
      : panel.getByRole("button", { name: words.global, exact: true });
    await button.click();
    await expect.poll(() => writes.length).toBe(1);
    await expect(page.locator("[data-memory-processing]").locator('input[type="time"]')).toBeDisabled();
    await expect(panel.locator('[data-unsaved-experience="2"]').getByRole("button", { name: words.discard, exact: true })).toBeDisabled();
    expect(writes[0].path.endsWith(individual ? "/situations/1/recheck" : "/memory/recheck")).toBe(true);
    expect(Object.keys(writes[0].body).sort()).toEqual(individual ? ["expected_receipt_version", "expected_version", "idempotency_key"] : ["expected_version", "idempotency_key"]);
    controls.finishRecheck = true; finish(); controls.barrier = null;
    await expect(panel.getByText(words.result, { exact: true })).toBeVisible();
    await expect(page.locator("[data-memory-processing]").locator('input[type="time"]')).toBeEnabled();
    expect(writes).toHaveLength(1);
  });

  test(`late previous-scope list and wrong request result never replace current evidence (${language})`, async ({ page }, info) => {
    const { panel, controls, writes } = await fixture(page, info, language);
    controls.wrongKey = true;
    await panel.locator('[data-unsaved-experience="1"]').getByRole("button", { name: words.recheck, exact: true }).click();
    await expect(panel.getByRole("alert")).toBeVisible();
    await expect(panel.getByText(words.result, { exact: true })).toHaveCount(0);
    let finish!: () => void; controls.listBarrier = new Promise(resolve => { finish = resolve; });
    await page.reload();
    await expect.poll(() => controls.listWaiting).toBe(true);
    await page.locator("select").nth(1).selectOption(SECOND);
    await expect(page.locator("[data-memory-unsaved]").getByText(words.none, { exact: true })).toBeVisible();
    finish(); controls.listBarrier = null;
    await expect(page.locator("[data-memory-unsaved]").locator("[data-unsaved-experience]")).toHaveCount(0);
    await expect(page.locator("[data-memory-unsaved]").getByRole("alert")).toHaveCount(0);
    expect(writes).toHaveLength(1);
  });

  test(`worker error is resumable and never displayed as a completed partial result (${language})`, async ({ page }, info) => {
    const { panel, controls, writes } = await fixture(page, info, language);
    controls.workerError = true; controls.finishRecheck = true;
    await panel.getByRole("button", { name: words.global, exact: true }).click();
    await expect(panel.getByRole("alert")).toBeVisible();
    await expect(panel.getByText(words.result, { exact: true })).toHaveCount(0);
    controls.workerError = false;
    await panel.getByRole("button", { name: words.retry, exact: true }).click();
    await expect(panel.getByText(words.result, { exact: true })).toBeVisible();
    expect(writes).toHaveLength(2); expect(writes[1]).toEqual(writes[0]);
  });
}
