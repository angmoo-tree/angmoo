import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { installWorldCharacterManagementFixture, syntheticWorldCharacter, WORLD_AGENT } from "./world-character-management-fixture";
import { FEED_WORLD } from "./world-feed-fixture";
import { memoryBatchFixture } from "./memory-batch-fixture";
const SECOND = "01a0f751-3bfb-7388-a914-400990cd56a0";

async function fixture(page: Page, info: TestInfo, language: "ko" | "en") {
  await installWorldCharacterManagementFixture(page, info.project.name === "static-export", String(info.project.use.baseURL), language);
  const scope = { world_id: FEED_WORLD, subject_world_character_id: WORLD_AGENT };
  const state = { scope, version: 1, memory_enabled: true, daily_enabled: false, local_time: "22:30", timezone: "Asia/Seoul",
    shutdown_apply_enabled: true, next_due_at: null, last_applied_at: null as string | null, pending_count: 3,
    blocked_count: 0, applied_count: 0, status: "idle", result: null as string | null };
  const writes: { path: string; body: Record<string, unknown> }[] = [];
  const controls = { timeout: false, barrier: null as Promise<void> | null,
    resolvedKey: null as string | null,
    readBarrier: null as Promise<void> | null, waitingRead: false };
  const batch = memoryBatchFixture(FEED_WORLD, WORLD_AGENT, () => state.memory_enabled);
  const secondBatch = memoryBatchFixture(FEED_WORLD, SECOND, () => state.memory_enabled);
  await page.route(info.project.name === "static-export" ? "http://127.0.0.1:8080/api/v1/**" : "**/api/backend/**", async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (path.endsWith(`/worlds/${FEED_WORLD}/world-characters`)) return route.fulfill({ json: {
      schema_version: "world-character-profile-list-v1", world_id: FEED_WORLD,
      items: [syntheticWorldCharacter(WORLD_AGENT).profile, syntheticWorldCharacter(SECOND).profile] } });
    const second = path.includes(`/world-characters/${SECOND}/`);
    const activeScope = second ? { ...scope, subject_world_character_id: SECOND } : scope;
    if (!second && !path.includes(`/world-characters/${WORLD_AGENT}/`)) return route.fallback();
    if (request.method() !== "GET") writes.push({ path, body: request.postDataJSON() });
    if (path.endsWith("/memory/unsaved-experiences")) return route.fulfill({ json: {
      schema_version: "memory-unsaved-experiences.v1", scope: activeScope, items: [], next_cursor: null,
      blocked_count: 0, scope_busy: false, can_recheck: false,
    } });
    if (path.endsWith("/memory/processing-settings")) {
      if (second) return route.fulfill({ json: { ...state, scope: { ...scope, subject_world_character_id: SECOND }, pending_count: 77, local_time: "06:10" } });
      if (request.method() === "GET" && controls.readBarrier) { controls.waitingRead = true; await controls.readBarrier; }
      if (request.method() === "PUT") {
        const body = request.postDataJSON(); expect(body.expected_version).toBe(state.version);
        Object.assign(state, { daily_enabled: body.daily_enabled, local_time: body.local_time,
          shutdown_apply_enabled: body.shutdown_apply_enabled, version: state.version + 1 });
      }
      const key = new URL(request.url()).searchParams.get("request_key");
      return route.fulfill({ json: { ...state, resolved_request_key: key && key === controls.resolvedKey ? key : null } });
    }
    if (path.endsWith("/memory/save")) {
      expect(request.method()).toBe("POST");
      expect(Object.keys(request.postDataJSON()).sort()).toEqual(["expected_version", "idempotency_key"]);
      if (controls.timeout) { controls.timeout = false; return route.abort("failed"); }
      if (controls.barrier) await controls.barrier;
      Object.assign(state, { result: state.pending_count ? "accepted" : "empty", status: state.pending_count ? "accepted" : "idle" });
      return route.fulfill({ status: 202, json: state });
    }
    if (await (second ? secondBatch : batch)(route)) return;
    const capabilities = { read: "available", mutate: "available" };
    if (path.endsWith("/memory/settings")) return route.fulfill({ json: {
      schema_version: "memory-setting-read.v1", scope: activeScope, configured: true, enabled: state.memory_enabled,
      retention_days: 180, provider_mode: "optional-configured", version: 1, capabilities } });
    if (path.endsWith("/memories")) return route.fulfill({ json: {
      schema_version: "memory-item-list.v1", scope: activeScope, memory_enabled: state.memory_enabled, items: [], next_cursor: null, capabilities } });
    return route.fulfill({ status: 404, json: { detail: "unexpected_memory_fixture_request" } });
  });
  await page.goto(`/memory?world=${FEED_WORLD}&subject=${WORLD_AGENT}`);
  return { state, writes, controls, panel: page.locator("[data-memory-processing]") };
}

for (const language of ["ko", "en"] as const) {
  test(`three independent roles, drafts, deferred apply and mobile layout (${language})`, async ({ page }, info) => {
    const { state, writes, panel } = await fixture(page, info, language);
    const save = panel.getByRole("button", { name: language === "ko" ? "지금 기억 저장" : "Save memories now", exact: true });
    await expect(save).toBeEnabled();
    await save.focus(); await expect(save).toBeFocused();
    await expect(page.getByRole("button", { name: language === "ko" ? "지금 관계 정리" : "Review relationships now", exact: true })).toBeVisible();
    await panel.getByRole("checkbox").first().check();
    await panel.locator('input[type="time"]').fill("21:20");
    await expect(panel.getByText(language === "ko"
      ? "부하가 한 번에 몰리지 않도록 기억 정리와 일일 관계 정리는 시간을 띄워 예약하는 것을 권장해요. 실행 시각은 직접 설정할 수 있어요."
      : "To help spread the workload, schedule memory consolidation and daily relationship review at different times. You can choose the times.", {exact: true})).toBeVisible();
    expect(writes).toHaveLength(0);
    await save.click();
    await expect(save).toBeDisabled();
    expect(writes).toHaveLength(1);
    expect(state.daily_enabled).toBe(false); expect(state.local_time).toBe("22:30");
    Object.assign(state, { status: "saved", pending_count: 0, applied_count: 3, last_applied_at: "2026-10-08T08:00:00Z" });
    await expect(panel.getByText(language === "ko" ? "저장 대기 0개" : "0 waiting to be saved")).toBeVisible();
    await expect(save).toBeDisabled();
    await expect(panel.locator('input[type="time"]')).toHaveValue("21:20");
    await panel.getByRole("button", { name: language === "ko" ? "기억 저장 설정 저장" : "Save memory saving settings", exact: true }).click();
    await expect.poll(() => state.daily_enabled).toBe(true);
    expect(writes.filter(row => row.path.endsWith("/memory/save"))).toHaveLength(1);
    for (const width of [390, 1100]) {
      await page.setViewportSize({ width, height: 980 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
      await panel.screenshot({ path: `../artifacts/situation-validation/${info.project.name}-${language}-${width}.png` });
    }
    await panel.getByRole("checkbox").first().focus();
    await expect(panel.getByRole("checkbox").first()).toBeFocused();
  });

  test(`empty, OFF, timeout and duplicate click retain request identity (${language})`, async ({ page }, info) => {
    const { state, writes, controls, panel } = await fixture(page, info, language);
    const save = panel.getByRole("button", { name: language === "ko" ? "지금 기억 저장" : "Save memories now", exact: true });
    await expect(save).toBeEnabled();
    controls.timeout = true;
    await save.click();
    await expect(panel.getByRole("alert")).toBeVisible();
    expect(writes).toHaveLength(1);
    let finish!: () => void; controls.barrier = new Promise(resolve => { finish = resolve; });
    const button = await save.elementHandle();
    await save.click();
    await expect.poll(() => writes.length).toBe(2);
    expect(writes[1].body).toEqual(writes[0].body);
    await button!.evaluate(element => { (element as HTMLButtonElement).click(); (element as HTMLButtonElement).click(); });
    expect(writes).toHaveLength(2);
    state.pending_count = 0; finish(); controls.barrier = null;
    await expect(panel.getByText(language === "ko" ? "지금 저장할 경험이 없어요." : "There are no experiences to save right now.")).toBeVisible();
    await expect(save).toBeDisabled();
    await save.evaluate(element => { (element as HTMLButtonElement).click(); });
    expect(writes).toHaveLength(2);
    state.memory_enabled = false;
    await expect(save).toBeDisabled();
    expect(writes).toHaveLength(2);
  });

  test(`a timed-out accepted save is resolved by reads before the next manual save (${language})`, async ({ page }, info) => {
    const { state, writes, controls, panel } = await fixture(page, info, language);
    const save = panel.getByRole("button", { name: language === "ko" ? "지금 기억 저장" : "Save memories now", exact: true });
    controls.timeout = true;
    await save.click();
    await expect(panel.getByRole("alert")).toBeVisible();
    const firstKey = String(writes[0].body.idempotency_key);
    controls.resolvedKey = firstKey;
    Object.assign(state, { status: "saved", pending_count: 0, applied_count: 3, last_applied_at: "2026-10-08T08:00:00Z" });
    await expect(panel.getByRole("alert")).not.toBeVisible();
    await expect(save).toBeDisabled();
    expect(writes).toHaveLength(1);
    state.pending_count = 2;
    await expect(save).toBeEnabled();
    await save.click();
    await expect.poll(() => writes.length).toBe(2);
    expect(writes[1].body.idempotency_key).not.toBe(firstKey);
  });

  test(`a late response from the previous character cannot replace current settings (${language})`, async ({ page }, info) => {
    const { controls, panel } = await fixture(page, info, language);
    await expect(panel).toBeVisible();
    let release!: () => void;
    controls.readBarrier = new Promise(resolve => { release = resolve; });
    await expect.poll(() => controls.waitingRead).toBe(true);
    await page.locator("select").nth(1).selectOption(SECOND);
    await expect(panel.locator('input[type="time"]')).toHaveValue("06:10");
    release(); controls.readBarrier = null;
    await expect(panel.getByText(language === "ko" ? "저장 대기 77개" : "77 waiting to be saved")).toBeVisible();
    await expect(panel.locator('input[type="time"]')).toHaveValue("06:10");
  });

  test(`canonical situation detail is readable before search preparation with a deleted original (${language})`, async ({ page }, info) => {
    await fixture(page, info, language);
    const scope = { world_id: FEED_WORLD, subject_world_character_id: WORLD_AGENT };
    const item = { id: "situation-fixture", memory_kind: "AUTOBIOGRAPHICAL_EVENT", summary: "SITUATION_CANONICAL_SUMMARY",
      lifecycle: "active", formed_at: "2026-10-08T08:00:00Z", valid_from: "2026-10-08T07:00:00Z", valid_until: null,
      pinned: false, superseded_by_memory_id: null, retention_days: 180, related_character: null, version: 1 };
    await page.route(`**/world-characters/${WORLD_AGENT}/memories**`, route => {
      const detail = new URL(route.request().url()).pathname.endsWith(item.id);
      return route.fulfill({ json: detail ? { ...item, schema_version: "memory-item-detail.v1", scope,
        capabilities: { read: "available", mutate: "available" }, memory_enabled: true, evidence: [], provenance_summary: "",
        episode: { representation: "activity_situation_v1", partial: true, omitted_units: 0, followup_count: 0,
          units: [{ sources: [{ role: "core", status: "missing", text: null },
            { role: "committed_result", status: "verified", text: "SAVED_RESULT" }],
            thought: { status: "recorded", text: "SAVED_THOUGHT", truncated: false } }] } }
        : { schema_version: "memory-item-list.v1", scope, memory_enabled: true, items: [item], next_cursor: null,
          capabilities: { read: "available", mutate: "available" } } });
    });
    await page.reload();
    await page.getByRole("button", { name: new RegExp(item.summary) }).click();
    const detail = page.getByRole("region", { name: language === "ko" ? "상황에 연결된 원문과 생각" : "Source text and thoughts connected to this situation" });
    await expect(detail.getByText("SAVED_RESULT", { exact: false })).toBeVisible();
    await expect(detail.getByText("SAVED_THOUGHT", { exact: false })).toBeVisible();
    await expect(detail.getByText(language === "ko" ? "원문이 없습니다." : "The source text is missing.", { exact: false })).toBeVisible();
    expect(await detail.locator("a").count()).toBe(0);
    await expect(page.getByRole("button", { name: language === "ko" ? "고정" : "Pin", exact: true })).toBeVisible();
  });
}
