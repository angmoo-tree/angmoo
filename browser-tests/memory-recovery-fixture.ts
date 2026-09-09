import { expect, type Page } from "@playwright/test";
import { json } from "./continuity-next-fixture";

export async function verifyMemoryRecovery(page: Page, worldId: string) {
  const subjectId = "memory-recovery-bird";
  const scope = { world_id: worldId, subject_world_character_id: subjectId };
  const capabilities = { read: "available", mutate: "available" };
  const item = { id: "retained-memory", memory_kind: "AUTOBIOGRAPHICAL_EVENT",
    summary: "훈련을 마치고 약속을 지켰어.", lifecycle: "active", formed_at: "2026-09-09T01:00:00Z",
    valid_from: "2026-09-09T01:00:00Z", valid_until: null, pinned: false,
    superseded_by_memory_id: null, retention_days: 180, related_character: null, version: 1 };
  let retried = 0;
  await page.route(`**/worlds/${worldId}/world-characters**`, async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/world-characters")) return json(route, {
      schema_version: "world-character-profile-list-v1", world_id: worldId,
      items: [{ schema_version: "world-character-profile-v1", ...scope, character_id: "fixture-bird",
        world_character_id: subjectId, display_name: "기억하는 앵무", handle: "memory_bird", avatar_url: null,
        banner_url: null, intro: "기억 복구", role_key: "mentor", control_mode: "autonomous", status: "active", profile_capability: "available" }] });
    if (path.endsWith("/memory/batch-retry") || path.endsWith("/memory/batch-settings")) {
      const retry = path.endsWith("/batch-retry");
      if (retry) retried++;
      return json(route, { scope, version: 1, ai_enabled: true, memory_enabled: true,
        shutdown_enabled: true, schedule_enabled: true, local_time: "23:51", timezone: "Asia/Seoul",
        next_due_at: "2026-09-09T14:51:00Z", model_id: "gemini-3.5-flash-lite", profile_version: 1,
        pending_count: retried && !retry ? 0 : 2, status: retry ? "pending" : retried ? "completed" : "attention",
        last_code: retried ? null : "memory_selection_output_incomplete",
        last_completed_at: retried && !retry ? "2026-09-09T01:00:00Z" : null,
        available_models: ["gemini-3.5-flash-lite"] });
    }
    if (path.endsWith("/memory/settings")) return json(route, {
      schema_version: "memory-setting-read.v1", scope, configured: true, enabled: true,
      retention_days: 180, provider_mode: "none", version: 1, capabilities });
    if (path.endsWith("/memories")) return json(route, {
      schema_version: "memory-item-list.v1", scope, memory_enabled: true, items: retried ? [item] : [], next_cursor: null, capabilities });
    if (path.endsWith("/memories/retained-memory")) return json(route, {
      ...item, schema_version: "memory-item-detail.v1", scope, capabilities,
      evidence: [{ source_kind: "CHAT_MESSAGE", source_label: "대화", source_created_at: item.formed_at,
        availability: "available", excerpt: "훈련 뒤 약속을 확인했어.", related_character: null,
        canonical_href: `/worlds/${worldId}/chat/fixture-thread` }], provenance_summary: "현재 확인 가능한 근거 1개 / 전체 1개" });
    return route.fallback();
  });
  await page.goto(`/memory?world=${worldId}&subject=${subjectId}`);
  await expect(page.getByText("아직 저장된 기억이 없어요")).toBeVisible();
  await expect(page.getByText("AI 정리 응답을 정상적으로 완료하지 못했어요. 경험은 보관되어 있으니 다시 시도해 주세요.")).toBeVisible();
  await page.getByRole("button", { name: "실패한 정리 다시 시도" }).click();
  await expect(page.getByText(item.summary, { exact: true })).toBeVisible({ timeout: 15000 });
  await page.getByText(item.summary, { exact: true }).click();
  await expect(page.getByText("훈련 뒤 약속을 확인했어.")).toBeVisible();
  expect(retried).toBe(1);
}
