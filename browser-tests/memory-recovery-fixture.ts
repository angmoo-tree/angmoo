import { expect, type Page } from "@playwright/test";
import { json } from "./continuity-next-fixture";
import { memoryBatchFixture } from "./memory-batch-fixture";

export async function verifyMemoryRecovery(page: Page, worldId: string) {
  const subjectId = "memory-recovery-bird";
  const scope = { world_id: worldId, subject_world_character_id: subjectId };
  const capabilities = { read: "available", mutate: "available" };
  const item = { id: "retained-memory", memory_kind: "AUTOBIOGRAPHICAL_EVENT",
    summary: "훈련을 마치고 약속을 지켰어.", lifecycle: "active", formed_at: "2026-09-09T01:00:00Z",
    valid_from: "2026-09-09T01:00:00Z", valid_until: null, pinned: false,
    superseded_by_memory_id: null, retention_days: 180, related_character: null, version: 1 };
  const batch = memoryBatchFixture(worldId, subjectId, () => true);
  let retried = 0;
  let completed = false;
  const keys: string[] = [];
  const processing = () => ({ scope, version: 1, memory_enabled: true, daily_enabled: false,
    local_time: "23:51", timezone: "Asia/Seoul", shutdown_apply_enabled: true,
    next_due_at: null, last_applied_at: completed ? "2026-09-09T01:00:00Z" : null,
    pending_count: completed ? 0 : 1, blocked_count: 0, applied_count: completed ? 1 : 0,
    status: completed ? "saved" : "partial_error", result: completed ? "accepted" : null,
    scope_busy: false, can_recheck: false });
  await page.route(`**/worlds/${worldId}/world-characters**`, async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/world-characters")) return json(route, {
      schema_version: "world-character-profile-list-v1", world_id: worldId,
      items: [{ schema_version: "world-character-profile-v1", ...scope, character_id: "fixture-bird",
        world_character_id: subjectId, display_name: "기억하는 앵무", handle: "memory_bird", avatar_url: null,
        banner_url: null, intro: "기억 복구", role_key: "mentor", control_mode: "autonomous", status: "active", profile_capability: "available" }] });
    if (path.endsWith("/memory/processing-settings")) return json(route, processing());
    if (path.endsWith("/memory/unsaved-experiences")) return json(route, {
      scope, items: [], next_cursor: null, blocked_count: 0, scope_busy: false, can_recheck: false });
    if (path.endsWith("/memory/save")) {
      const body = route.request().postDataJSON();
      keys.push(body.idempotency_key);
      expect(body.expected_version).toBe(1);
      retried++;
      if (retried === 1) return route.abort("failed");
      expect(keys[1]).toBe(keys[0]);
      completed = true;
      return json(route, processing());
    }
    if (await batch(route)) return;
    if (path.endsWith("/memory/settings")) return json(route, {
      schema_version: "memory-setting-read.v1", scope, configured: true, enabled: true,
      retention_days: 180, provider_mode: "none", version: 1, capabilities });
    if (path.endsWith("/memories")) return json(route, {
      schema_version: "memory-item-list.v1", scope, memory_enabled: true, items: completed ? [item] : [], next_cursor: null, capabilities });
    if (path.endsWith("/memories/retained-memory")) return json(route, {
      ...item, schema_version: "memory-item-detail.v1", scope, capabilities,
      evidence: [{ source_kind: "CHAT_MESSAGE", source_label: "대화", source_created_at: item.formed_at,
        availability: "available", excerpt: "훈련 뒤 약속을 확인했어.", related_character: null,
        canonical_href: `/worlds/${worldId}/chat/fixture-thread` }], provenance_summary: "현재 확인 가능한 근거 1개 / 전체 1개" });
    return route.fallback();
  });
  await page.goto(`/memory?world=${worldId}&subject=${subjectId}`);
  await expect(page.getByText("아직 저장된 기억이 없어요")).toBeVisible();
  await expect(page.getByText("일부 경험을 저장하지 못했어요. 저장된 기억은 유지됩니다.")).toBeVisible();
  await page.getByRole("button", { name: "지금 기억 저장", exact: true }).click();
  await expect(page.getByText("기억 저장 요청을 완료하지 못했어요. 다시 누르면 같은 요청을 확인합니다.")).toBeVisible();
  await page.getByRole("button", { name: "지금 기억 저장", exact: true }).click();
  await expect(page.getByText(item.summary, { exact: true })).toBeVisible({ timeout: 15000 });
  await page.getByText(item.summary, { exact: true }).click();
  await expect(page.getByText("훈련 뒤 약속을 확인했어.")).toBeVisible();
  expect(retried).toBe(2);
  expect(new Set(keys).size).toBe(1);
}
